# -*- coding: utf-8 -*-
"""
Script para dimensionar muros en planta
Crea dimensiones automáticas de muros en la vista activa (Floor Plan o Structural Plan)
con soporte para muros rectos y arcos
"""

import clr
import json
import os
import time
import traceback
import math

# Revit API References
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import TaskDialog
from Autodesk.Revit.Exceptions import OperationCanceledException

# pyRevit Imports
from pyrevit import forms, script, revit

# System Collections
from System.Collections.Generic import List

# Initialize Logger
logger = script.get_logger()

# Constants
OFFSET_MULTIPLIER_INCREMENT = 10
DEFAULT_OFFSET_MM = 1000  # Default offset in millimetres
TOLERANCE = 0.01  # Constant tolerance value

# Initialize Revit Document
doc = revit.doc
uidoc = revit.uidoc

# ============================================
# Configuration Management
# ============================================
class Config:
    """
    Handles loading, saving, and managing user configuration.
    """
    def __init__(self):
        self.config_path = os.path.join(os.path.dirname(__file__), 'dimension_walls_config.json')
        self.data = self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load config: {}".format(str(e)))
                return {}
        return {}

    def save(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save config: {}".format(str(e)))

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def remove(self, key):
        self.data.pop(key, None)


# ============================================
# Unit Conversion Utility
# ============================================
def mm_to_internal(mm):
    """Convert millimeters to internal Revit units"""
    return DB.UnitUtils.ConvertToInternalUnits(mm, DB.UnitTypeId.Millimeters)


def internal_to_mm(internal):
    """Convert internal Revit units to millimeters"""
    return DB.UnitUtils.ConvertFromInternalUnits(internal, DB.UnitTypeId.Millimeters)


def get_id_value(element_id):
    """Get integer value from ElementId - compatible with Revit 2024+."""
    if hasattr(element_id, "Value"):
        return element_id.Value
    elif hasattr(element_id, "IntegerValue"):
        return element_id.IntegerValue
    else:
        return int(str(element_id))


# ============================================
# User Interface Management
# ============================================
def get_offset_distance():
    """
    Prompts the user to input the offset distance in millimetres.
    """
    # Try to load default from config
    config = Config()
    default_offset = config.get('default_offset_mm', DEFAULT_OFFSET_MM)
    
    offset_distance_str = forms.ask_for_string(
        default=str(default_offset),
        prompt="Enter the offset distance (in millimetres):",
        title="Offset Distance",
    )
    if offset_distance_str:
        try:
            offset_distance = float(offset_distance_str)
            if offset_distance <= 0:
                TaskDialog.Show("Error", "Offset distance must be a positive number.")
                return None
            # Save to config
            config.set('default_offset_mm', offset_distance)
            config.save()
            return offset_distance
        except ValueError:
            TaskDialog.Show("Error", "Invalid input. Please enter a valid number.")
            return None
    else:
        return None


    return forms.ask_for_one_item(
        dimensioning_options,
        default="Wall Thickness",
        title="Dimensioning Type",
    )

def get_valid_dimension_types(doc):
    """Get all valid linear dimension types."""
    return sorted(
        [dt for dt in DB.FilteredElementCollector(doc).OfClass(DB.DimensionType).ToElements() 
         if dt.StyleType == DB.DimensionStyleType.Linear],
        key=lambda x: x.Name
    )

def get_config_ui(doc):
    """
    Unified configuration UI.
    """
    # 1. Dimension Styles
    dim_types = get_valid_dimension_types(doc)
    if not dim_types:
        forms.alert("No linear dimension types found in project.", exitscript=True)
        return None

    dim_type_names = [dt.Name for dt in dim_types]
    
    # Defaults
    config = Config()
    last_offset = config.get('default_offset_mm', DEFAULT_OFFSET_MM)
    
    # We can use a FlexForm or sequential. Let's use sequential for simplicity and robustness.
    
    # Step 1: Style
    sel_dim_type = forms.SelectFromList.show(
        dim_types,
        name_attr='Name',
        title='Select Dimension Style',
        button_name='Next'
    )
    if not sel_dim_type: return None
    
    # Defaults
    sel_face = "External" # Internal default, no user prompt
    
    # Step 2: Type (Thickness/Overall)
    sel_method = get_dimensioning_type()
    if not sel_method: return None
    
    # Step 3: Offset
    offset_str = forms.ask_for_string(
        default=str(last_offset),
        prompt="Offset Distance (mm):",
        title="Offset"
    )
    if not offset_str: return None
    try:
        offset_val = float(offset_str)
        config.set('default_offset_mm', offset_val)
        config.save()
    except:
        forms.alert("Invalid offset")
        return None
        
    # Step 5: Scope
    options = {
        'Process Active View': 'view',
        'Process Selection': 'selection'
    }
    scope_prompt = forms.CommandSwitchWindow.show(
        list(options.keys()),
        message='Select Process Scope:'
    )
    if not scope_prompt: return None
    sel_scope = options[scope_prompt]
    
    return {
        'dim_type': sel_dim_type,
        'face': sel_face,
        'method': sel_method,
        'offset_mm': offset_val,
        'scope': sel_scope
    }



def get_user_input():
    """Deprecated - Replaced by get_config_ui"""
    pass


# ============================================
# Geometry Handling
# ============================================
_wall_vector_cache = {}


def get_wall_vectors(wall):
    """Get wall direction and perpendicular direction vectors"""
    wall_id = get_id_value(wall.Id)
    if wall_id in _wall_vector_cache:
        return _wall_vector_cache[wall_id]

    loc_curve = wall.Location.Curve
    if isinstance(loc_curve, DB.Line):
        wall_dir = loc_curve.Direction.Normalize()
    elif isinstance(loc_curve, DB.Arc):
        param = 0.5  # Mid-point parameter
        try:
            derivatives = loc_curve.ComputeDerivatives(param, True)
            wall_dir = derivatives.BasisX.Normalize()
        except:
            # Fallback: use direction from start to end
            wall_dir = (loc_curve.GetEndPoint(1) - loc_curve.GetEndPoint(0)).Normalize()
    else:
        logger.warning("Unsupported curve type for wall location: {}. Defaulting to X direction.".format(type(loc_curve)))
        wall_dir = DB.XYZ.BasisX

    perp_dir = wall_dir.CrossProduct(DB.XYZ.BasisZ)
    if perp_dir.GetLength() < 0.001:
        # If wall is vertical, use Y direction as perpendicular
        perp_dir = DB.XYZ.BasisY
    
    perp_dir = perp_dir.Normalize()
    _wall_vector_cache[wall_id] = (wall_dir, perp_dir)
    return wall_dir, perp_dir


def get_wall_solid(wall, options=None):
    """Extract solid geometry from wall"""
    options = options or DB.Options()
    for geometry_object in wall.get_Geometry(options):
        if isinstance(geometry_object, DB.Solid) and geometry_object.Faces.Size > 0:
            return geometry_object
    return None


def get_wall_face_edges(wall, opts, dimension_face):
    """Get horizontal edges from wall faces for dimensioning - these represent the faces in plan view"""
    try:
        wall_solid = get_wall_solid(wall, opts)
        if not wall_solid:
            logger.warning("No solid geometry found for wall ID {}".format(wall.Id))
            return []

        edges = []
        # Get face references to identify which faces to use
        try:
            if dimension_face == "External":
                face_refs = list(DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Exterior))
            else:
                face_refs = list(DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Interior))
        except:
            face_refs = []

        # Find faces that match our selected face type
        target_faces = []
        for face in wall_solid.Faces:
            try:
                # Check if this face matches our target face reference
                if face.Reference:
                    for face_ref in face_refs:
                        if face_ref.ElementId == face.Reference.ElementId:
                            target_faces.append(face)
                            break
            except:
                continue

        # If we didn't find matching faces by reference, use all faces and filter by normal
        if not target_faces:
            for face in wall_solid.Faces:
                try:
                    normal = face.ComputeNormal(DB.UV(0.5, 0.5))
                    # Horizontal faces (perpendicular to Z axis) represent the wall faces in plan
                    if abs(abs(normal.DotProduct(DB.XYZ.BasisZ)) - 1.0) < 0.1:
                        target_faces.append(face)
                except:
                    continue

        # Get horizontal edges from target faces (edges parallel to XY plane)
        for face in target_faces:
            for edge_loop in face.EdgeLoops:
                for edge in edge_loop:
                    try:
                        edge_c = edge.AsCurve()
                        if isinstance(edge_c, DB.Line):
                            # Check if edge is horizontal (perpendicular to Z axis)
                            edge_dir = edge_c.Direction
                            if abs(edge_dir.DotProduct(DB.XYZ.BasisZ)) < 0.1:  # Horizontal edge
                                edges.append(edge)
                        elif isinstance(edge_c, DB.Arc):
                            # For arcs, check if they're horizontal
                            start = edge_c.GetEndPoint(0)
                            end = edge_c.GetEndPoint(1)
                            if abs(start.Z - end.Z) < 0.001:  # Horizontal arc
                                edges.append(edge)
                    except Exception as e:
                        logger.debug("Error processing edge for wall {}: {}".format(wall.Id, str(e)))
                        continue

        # Remove duplicates
        edge_endpoints = {}
        unique_edges = []
        for edge in edges:
            edge_c = edge.AsCurve()
            if isinstance(edge_c, DB.Line):
                start_point = edge_c.GetEndPoint(0)
                end_point = edge_c.GetEndPoint(1)
            elif isinstance(edge_c, DB.Arc):
                start_point = edge_c.GetEndPoint(0)
                end_point = edge_c.GetEndPoint(1)
            else:
                continue

            key = tuple(sorted([(start_point.X, start_point.Y, start_point.Z), 
                               (end_point.X, end_point.Y, end_point.Z)]))
            if key not in edge_endpoints:
                unique_edges.append(edge)
                edge_endpoints[key] = True
        
        return unique_edges
    except Exception as e:
        logger.error("Error occurred while processing wall {}: {}".format(wall.Id, str(e)))
        return []


def get_reference_position(edge, wall, dimension_line):
    """Get parameter position along wall for reference"""
    try:
        edge_curve = edge.AsCurve()
        edge_midpoint = edge_curve.Evaluate(0.5, True)
        wall_location = wall.Location.Curve
        intersection_result = dimension_line.Project(edge_midpoint)
        projected_point = intersection_result.XYZPoint
        position_result = wall_location.Project(projected_point)
        return position_result.Parameter
    except:
        # Fallback: use distance from start
        edge_curve = edge.AsCurve()
        edge_midpoint = edge_curve.Evaluate(0.5, True)
        wall_start = wall.Location.Curve.GetEndPoint(0)
        wall_dir = (wall.Location.Curve.GetEndPoint(1) - wall_start).Normalize()
        vec_to_midpoint = edge_midpoint - wall_start
        return vec_to_midpoint.DotProduct(wall_dir) / wall.Location.Curve.Length


def get_wall_end_references(wall, options):
    """Get references to wall end faces for length dimensioning."""
    wall_end_references = []
    try:
        # Strategy: Find faces perpendicular to wall direction
        wall_dir = None
        
        # Determine wall direction
        loc_curve = wall.Location.Curve
        if isinstance(loc_curve, DB.Line):
            wall_dir = loc_curve.Direction.Normalize()
        elif isinstance(loc_curve, DB.Arc):
            # For arc, we need references at the ends, which are perpendicular to tangent?
            # Actually, "Planar Face" at end of arc wall.
            # Simplest: use Strong references?
            pass
            
        wall_solid = get_wall_solid(wall, options)
        if not wall_solid: return []
        
        # Find vertical faces
        vertical_faces = []
        for face in wall_solid.Faces:
            try:
                normal = face.ComputeNormal(DB.UV(0.5, 0.5))
                if abs(normal.DotProduct(DB.XYZ.BasisZ)) < 0.1: # Horizontal normal = Vertical Face
                   vertical_faces.append(face)
            except: pass
            
        if not vertical_faces: return []
        
        # Sort faces?
        # Better: Find faces that are "Ends".
        # Ends usually have normal parallel to wall direction (for straight walls).
        
        if isinstance(loc_curve, DB.Line):
            target_faces = []
            for face in vertical_faces:
                normal = face.ComputeNormal(DB.UV(0.5, 0.5))
                # Allow parallel (Dot product ~1 or ~-1)
                if abs(abs(normal.DotProduct(wall_dir)) - 1.0) < 0.1:
                    target_faces.append(face)
            
            # Sort by position along wall dir
            if target_faces:
                # We expect 2 main end faces. There might be small ones.
                # Project centroid to line.
                sorted_faces = sorted(target_faces, key=lambda f: f.Evaluate(DB.UV(0.5,0.5)).DotProduct(wall_dir))
                
                # Pick First and Last
                if len(sorted_faces) >= 2:
                    wall_end_references.append(sorted_faces[0].Reference)
                    wall_end_references.append(sorted_faces[-1].Reference)
                    
        elif isinstance(loc_curve, DB.Arc):
             # For Arcs, end faces are naturally at the ends of the curve key parameters.
             # We can't use simple dot product.
             # But usually End Faces are planar.
             # We need 2 references at the "ends" of the arc.
             # Let's try to just collect all vertical side faces that are NOT Side faces (ShellLayerType).
             
             side_refs = set()
             try:
                 ext = DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Exterior)
                 int = DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Interior)
                 for r in ext: side_refs.add(r.ConvertToStableRepresentation(doc))
                 for r in int: side_refs.add(r.ConvertToStableRepresentation(doc))
             except: pass
             
             potential_ends = []
             for face in vertical_faces:
                 if face.Reference:
                     s_rep = face.Reference.ConvertToStableRepresentation(doc)
                     if s_rep not in side_refs:
                         potential_ends.append(face)
             
             if len(potential_ends) >= 2:
                 # Sort?
                 # Pick the two largest faces?
                 potential_ends.sort(key=lambda f: f.Area, reverse=True)
                 if len(potential_ends) >= 2:
                     wall_end_references.append(potential_ends[0].Reference)
                     wall_end_references.append(potential_ends[1].Reference)
                     
    except Exception as e:
        logger.debug("Error getting end references for wall {}: {}".format(wall.Id, str(e)))
        
    return wall_end_references


def find_end_faces(solid):
    """Find end faces of a wall solid"""
    end_faces = []
    try:
        longest_span = None
        max_length = 0
        for edge in solid.Edges:
            edge_curve = edge.AsCurve()
            if edge_curve.Length > max_length:
                longest_span = edge_curve
                max_length = edge_curve.Length
        
        if longest_span:
            longest_direction = (longest_span.GetEndPoint(1) - longest_span.GetEndPoint(0)).Normalize()
            for face in solid.Faces:
                try:
                    normal = face.ComputeNormal(DB.UV(0.5, 0.5))
                    cross_product = normal.CrossProduct(longest_direction)
                    if cross_product.GetLength() < 0.1:  # Faces perpendicular to longest direction
                        end_faces.append(face)
                except:
                    continue
    except Exception as e:
        logger.debug("Error finding end faces: {}".format(str(e)))
    return end_faces


# ============================================
# Revit API Utilities
# ============================================
def find_intersecting_walls(doc, wall):
    """Find walls that intersect with the given wall"""
    try:
        bbox = wall.get_BoundingBox(None)
        if not bbox:
            logger.debug("No bounding box found for wall ID {}".format(wall.Id))
            return set()

        outline = DB.Outline(bbox.Min, bbox.Max)
        intersecting_walls = {
            w for w in DB.FilteredElementCollector(doc)
            .OfClass(DB.Wall)
            .WherePasses(DB.BoundingBoxIntersectsFilter(outline))
            .WhereElementIsNotElementType()
            .ToElements() if w.Id != wall.Id
        }
        return intersecting_walls
    except Exception as e:
        logger.debug("Error finding intersecting walls: {}".format(str(e)))
        return set()


def is_space_free_for_dimension(doc, line, view):
    """Check if space is free for dimension line"""
    try:
        start_pt = line.GetEndPoint(0)
        end_pt = line.GetEndPoint(1)
        min_point = DB.XYZ(min(start_pt.X, end_pt.X), min(start_pt.Y, end_pt.Y), min(start_pt.Z, end_pt.Z))
        max_point = DB.XYZ(max(start_pt.X, end_pt.X), max(start_pt.Y, end_pt.Y), max(start_pt.Z, end_pt.Z))
        outline = DB.Outline(min_point, max_point)
        intersecting_dimensions = (
            DB.FilteredElementCollector(doc, view.Id)
            .OfCategory(DB.BuiltInCategory.OST_Dimensions)
            .WherePasses(DB.BoundingBoxIntersectsFilter(outline))
            .WhereElementIsNotElementType()
            .ToElements()
        )
        return len(intersecting_dimensions) == 0
    except:
        return True  # Assume free if check fails


def offset_dimension_line(line, offset_value, perp_dir):
    """Offset the dimension line in the direction perpendicular to the wall"""
    return line.CreateTransformed(DB.Transform.CreateTranslation(perp_dir.Multiply(offset_value)))


def find_free_space_for_dimension(doc, original_line, perp_dir, view):
    """Find free space for dimension line by offsetting if necessary"""
    line = original_line
    offset_multiplier = 1
    max_attempts = 10  # Prevent infinite loops
    while not is_space_free_for_dimension(doc, line, view) and offset_multiplier < max_attempts:
        offset_multiplier += 1
        offset_value = mm_to_internal(OFFSET_MULTIPLIER_INCREMENT * offset_multiplier)
        line = offset_dimension_line(original_line, offset_value, perp_dir)
        logger.debug("Offsetting dimension line by {}mm to find free space.".format(OFFSET_MULTIPLIER_INCREMENT * offset_multiplier))
    
    if offset_multiplier >= max_attempts:
        logger.warning("Max attempts reached for finding free space for dimension.")
        return None
    return line


def validate_references(ref_array, view):
    """Validate that references are valid and unique"""
    if ref_array is None or ref_array.Size < 2:
        return False, []
    
    # Check for null or invalid references
    valid_refs = []
    seen_refs = set()
    
    for i in range(ref_array.Size):
        ref = ref_array.get_Item(i)
        if ref is None:
            continue
        
        # Check if reference is valid
        try:
            # Try to get element from reference
            element = doc.GetElement(ref)
            if element is None:
                logger.debug("Reference element is None for reference index {}.".format(i))
                continue
            
            # Use StableRepresentation for accurate duplicate detection
            # This allows multiple distinct references (faces) from the same element
            try:
                ref_key = ref.ConvertToStableRepresentation(doc)
            except:
                # Fallback to string representation if StableRep fails
                ref_key = str(ref)
            
            if ref_key in seen_refs:
                logger.debug("Duplicate reference found (same face).")
                continue
            
            seen_refs.add(ref_key)
            valid_refs.append(ref)
            logger.debug("Valid reference added from element ID {}.".format(get_id_value(ref.ElementId)))
        except Exception as e:
            logger.debug("Exception validating reference index {}: {}.".format(i, str(e)))
            continue
    
    logger.debug("Validation result: {} valid references from {} total.".format(len(valid_refs), ref_array.Size))
    return len(valid_refs) >= 2, valid_refs


def create_arc_length_dimension(doc, view, arc, arc_ref, first_ref, second_ref):
    """
    Creates an arc length dimension for arc walls.
    Note: This requires Revit 2024+ API. For older versions, falls back to linear dimension.
    """
    try:
        # Validate references
        if first_ref is None or second_ref is None:
            logger.warning("Invalid references for arc length dimension.")
            return None
        
        ref_array = DB.ReferenceArray()
        ref_array.Append(first_ref)
        ref_array.Append(second_ref)
        
        # Try to use NewArcLengthDimension (Revit 2024+)
        try:
            dimension = doc.Create.NewArcLengthDimension(view, arc, arc_ref, ref_array)
            logger.info("Successfully created arc length dimension.")
            return dimension
        except AttributeError:
            # Fallback for older Revit versions: create linear dimension instead
            logger.warning("Arc length dimension not available in this Revit version. Creating linear dimension.")
            # Create a line dimension as fallback
            start_pt = arc.GetEndPoint(0)
            end_pt = arc.GetEndPoint(1)
            dim_line = DB.Line.CreateBound(start_pt, end_pt)
            dimension = doc.Create.NewDimension(view, dim_line, ref_array)
            return dimension
            
    except Exception as e:
        logger.error("Failed to create arc length dimension: {}".format(str(e)))
        logger.debug(traceback.format_exc())
        return None


# ============================================
# Wall Collection
# ============================================
def collect_walls_from_view(doc, view_id):
    """Collect walls visible in the active view"""
    try:
        wall_collector = (
            DB.FilteredElementCollector(doc, view_id)
            .OfCategory(DB.BuiltInCategory.OST_Walls)
            .WhereElementIsNotElementType()
            .ToElements()
        )
        logger.debug("Collected {} walls from view ID {}.".format(len(wall_collector), view_id))
        return wall_collector
    except Exception as e:
        logger.error("Error collecting walls: {}".format(str(e)))
        return []

def collect_walls_from_selection(doc):
    """Collect selected walls"""
    try:
        selection = uidoc.Selection.GetElementIds()
        if not selection:
            return []
            
        walls = []
        for eid in selection:
            elem = doc.GetElement(eid)
            if elem and isinstance(elem, DB.Wall):
                walls.append(elem)
        return walls
    except:
        return []

def create_preview_lines(doc, view, start_pt, end_pt):
    """Create a temporary model line for preview."""
    try:
        # Create line
        geom_line = DB.Line.CreateBound(start_pt, end_pt)
        
        # Create SketchPlane
        # Note: Model lines need sketch plane. In Plan View, Level plane.
        
        # This is complex in transaction.
        # Simplified Preview: Just count?
        # Or Just use logic: if user approves "Preview", we commit? 
        # Actually TransactionGroup allows Rollback.
        # "Preview" -> Run script in TransactionGroup -> Show Result -> Commit or Rollback?
        pass
    except:
        pass


# ============================================
# Main Dimension Creation Logic
# ============================================
def create_wall_dimensions(doc, view, selected_face, offset_distance, selected_dimensioning_type, dim_type, walls_override=None):
    """Main function to create wall dimensions in the active view"""
    existing_dim_endpoints = set()
    total_dimensions_created = 0
    total_walls_processed = 0

    # Get walls
    if walls_override:
        walls_in_view = walls_override
    else:
        walls_in_view = collect_walls_from_view(doc, view.Id)
        
    if not walls_in_view:
        logger.info("No walls found.")
        return 0, 0

    geometry_options = DB.Options()
    geometry_options.ComputeReferences = True
    geometry_options.IncludeNonVisibleObjects = True
    geometry_options.View = view

    for wall in walls_in_view:
        total_walls_processed += 1
        try:
            wall_dir, perp_dir = get_wall_vectors(wall)
            existing_line = wall.Location.Curve

            # Get wall face references
            try:
                wall_ext_face_refs = list(DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Exterior))
                wall_int_face_refs = list(DB.HostObjectUtils.GetSideFaces(wall, DB.ShellLayerType.Interior))
            except:
                logger.warning("Could not get face references for wall ID {}".format(wall.Id))
                continue

            if not wall_ext_face_refs or not wall_int_face_refs:
                logger.debug("Wall ID {} does not have both exterior and interior faces.".format(wall.Id))
                continue

            wall_ext_face_ref = wall_ext_face_refs[0]
            wall_int_face_ref = wall_int_face_refs[0]

            offset_dir = perp_dir.Negate() if selected_face == "External" else perp_dir
            original_off_crv = existing_line.CreateTransformed(
                DB.Transform.CreateTranslation(offset_dir.Multiply(offset_distance))
            )
            off_crv = original_off_crv

            vert_edge_sub = DB.ReferenceArray()
            is_arc_wall = isinstance(existing_line, DB.Arc)
            arc = existing_line if is_arc_wall else None
            arc_ref = wall_ext_face_ref if is_arc_wall else None

            if selected_dimensioning_type == "Wall Thickness":
                # For wall thickness, we need references from both sides of the wall
                # Use face references directly - they work better than edge references
                selected_face_ref = wall_ext_face_ref if selected_face == "External" else wall_int_face_ref
                opposite_face_ref = wall_int_face_ref if selected_face == "External" else wall_ext_face_ref
                
                # Add the selected face reference
                try:
                    test_element = doc.GetElement(selected_face_ref)
                    if test_element is not None:
                        vert_edge_sub.Append(selected_face_ref)
                        logger.debug("Added selected face reference for wall ID {}.".format(wall.Id))
                except Exception as e:
                    logger.debug("Could not add selected face reference for wall ID {}: {}.".format(wall.Id, str(e)))
                
                # Get face references from intersecting walls
                intersecting_walls = find_intersecting_walls(doc, wall)
                seen_wall_ids = {get_id_value(wall.Id)}
                found_intersecting_ref = False
                
                if intersecting_walls:
                    for int_wall in intersecting_walls:
                        if get_id_value(int_wall.Id) in seen_wall_ids:
                            continue
                        seen_wall_ids.add(get_id_value(int_wall.Id))
                        
                        try:
                            int_ext_face_refs = list(DB.HostObjectUtils.GetSideFaces(int_wall, DB.ShellLayerType.Exterior))
                            int_int_face_refs = list(DB.HostObjectUtils.GetSideFaces(int_wall, DB.ShellLayerType.Interior))
                            
                            if int_ext_face_refs and int_int_face_refs:
                                int_face_ref = int_ext_face_refs[0] if selected_face == "External" else int_int_face_refs[0]
                                # Validate before adding
                                try:
                                    test_element = doc.GetElement(int_face_ref)
                                    if test_element is not None:
                                        vert_edge_sub.Append(int_face_ref)
                                        found_intersecting_ref = True
                                        logger.debug("Added intersecting wall face reference for wall ID {}.".format(wall.Id))
                                        break  # Only need one intersecting wall reference
                                except:
                                    logger.debug("Invalid face reference for intersecting wall ID {}.".format(int_wall.Id))
                                    continue
                        except:
                            logger.debug("Could not get face references for intersecting wall ID {}.".format(int_wall.Id))
                            continue
                
                # If no intersecting walls found, use the opposite face of the same wall
                if not found_intersecting_ref:
                    try:
                        test_element = doc.GetElement(opposite_face_ref)
                        if test_element is not None:
                            vert_edge_sub.Append(opposite_face_ref)
                            logger.debug("Added opposite face reference for wall ID {}.".format(wall.Id))
                    except Exception as e:
                        logger.debug("Could not add opposite face reference for wall ID {}: {}.".format(wall.Id, str(e)))

                if vert_edge_sub.Size < 2:
                    logger.warning("Not enough references for wall ID {}. Found {} references.".format(wall.Id, vert_edge_sub.Size))
                    continue

                # Validate references before creating dimension
                is_valid, valid_refs = validate_references(vert_edge_sub, view)
                if not is_valid:
                    logger.debug("Invalid references for wall ID {}. Skipping.".format(wall.Id))
                    continue
                
                # Create new ReferenceArray with only valid references
                validated_ref_array = DB.ReferenceArray()
                for ref in valid_refs:
                    validated_ref_array.Append(ref)
                
                if validated_ref_array.Size < 2:
                    logger.debug("Not enough valid references for wall ID {}.".format(wall.Id))
                    continue

                # Create dimension
                if is_arc_wall and selected_dimensioning_type == "Overall":
                    # Note: This logic for arc overall inside thickness block is probably dead code or copy paste error in original? 
                    # "if selected_dimensioning_type == Wall Thickness" block should not handle Overall.
                    # But respecting original structure.
                    pass 
                    # Actually original had check here. But we are in Thickness branch.
                    # Let's keep thickness logic strictly for thickness.
                
                # Check for Linear Dimension creation (Thickness)
                line = find_free_space_for_dimension(doc, off_crv, perp_dir, view)
                if line is None:
                    logger.debug("No free space found for dimension line for wall ID {}".format(wall.Id))
                    continue

                dim_line = DB.Line.CreateBound(line.GetEndPoint(0), line.GetEndPoint(1))
                
                # Check if space is free (but don't skip if not - try anyway)
                space_free = is_space_free_for_dimension(doc, dim_line, view)
                if not space_free:
                    logger.debug("Dimension line space not free for wall ID {}, but continuing anyway.".format(wall.Id))
                
                dim_tuple = tuple(sorted([
                    (dim_line.GetEndPoint(0).X, dim_line.GetEndPoint(0).Y, dim_line.GetEndPoint(0).Z),
                    (dim_line.GetEndPoint(1).X, dim_line.GetEndPoint(1).Y, dim_line.GetEndPoint(1).Z)
                ]))
                
                if dim_tuple not in existing_dim_endpoints:
                    try:
                        logger.debug("Attempting to create dimension for wall ID {} with {} references.".format(wall.Id, validated_ref_array.Size))
                        if dim_type:
                            dim = doc.Create.NewDimension(view, dim_line, validated_ref_array, dim_type)
                        else:
                            dim = doc.Create.NewDimension(view, dim_line, validated_ref_array)
                        if dim:
                            existing_dim_endpoints.add(dim_tuple)
                            total_dimensions_created += 1
                            logger.info("Successfully created dimension for wall ID {}.".format(wall.Id))
                        else:
                            logger.warning("Dimension creation returned None for wall ID {}.".format(wall.Id))
                    except OperationCanceledException:
                        logger.warning("Dimension creation cancelled by user.")
                        continue
                    except Exception as e:
                        logger.error("Failed to create dimension for wall ID {}: {}".format(wall.Id, str(e)))
                        logger.error("Error details: {}".format(traceback.format_exc()))
                        continue
                else:
                    logger.debug("Duplicate dimension endpoint detected for wall ID {}. Skipping.".format(wall.Id))

            else:  # "Overall" method
                wall_end_references = get_wall_end_references(wall, geometry_options)
                
                # Create Reference Array
                validated_ref_array = DB.ReferenceArray()
                for ref in wall_end_references:
                    if ref: validated_ref_array.Append(ref)
                
                if validated_ref_array.Size < 2:
                    logger.debug("Not enough references for overall dim for wall ID {}.".format(wall.Id))
                    continue
                
                if is_arc_wall:
                     # Arc length dimension - Force it for Overall on Arc Wall
                     arc_ref = wall_ext_face_ref
                     
                     # Try Create
                     try:
                         if dim_type:
                            dim = doc.Create.NewArcLengthDimension(view, arc, arc_ref, validated_ref_array, dim_type)
                         else:
                            dim = doc.Create.NewArcLengthDimension(view, arc, arc_ref, validated_ref_array)
                            
                         if dim:
                            total_dimensions_created += 1
                     except:
                         # Fallback to internal face
                         try:
                             dim = doc.Create.NewArcLengthDimension(view, arc, wall_int_face_ref, validated_ref_array)
                             if dim: total_dimensions_created += 1
                         except Exception as e:
                                logger.warning("Failed to create Arc Length dimension for Wall {}: {}".format(wall.Id, str(e)))
                else:
                        # Linear dimension
                         line = find_free_space_for_dimension(doc, off_crv, perp_dir, view)
                         if line is None: continue

                         dim_line = DB.Line.CreateBound(line.GetEndPoint(0), line.GetEndPoint(1))
                         
                         try:
                            if dim_type:
                                dim = doc.Create.NewDimension(view, dim_line, validated_ref_array, dim_type)
                            else:
                                dim = doc.Create.NewDimension(view, dim_line, validated_ref_array)
                            
                            if dim:
                                total_dimensions_created += 1
                         except Exception as e:
                            logger.error("Failed to create dimension: {}".format(str(e)))

        except Exception as e:
            logger.error("Failed to process wall with ID {}: {}".format(wall.Id, str(e)))
            logger.debug(traceback.format_exc())
            continue
    
    logger.info("Created {} dimensions for {} walls processed.".format(total_dimensions_created, total_walls_processed))
    return total_dimensions_created, total_walls_processed


def get_active_view():
    """Get the currently active view and verify it's a plan view"""
    active_view = uidoc.ActiveView
    
    if not isinstance(active_view, DB.ViewPlan):
        forms.alert(
            "The active view must be a Floor Plan or Structural Plan.\n"
            "Current view type: {}".format(active_view.ViewType),
            exitscript=True
        )
        return None
    
    # ViewPlan can only be FloorPlan or EngineeringPlan, so if it's ViewPlan, it's valid
    if active_view.ViewType not in [DB.ViewType.FloorPlan, DB.ViewType.EngineeringPlan]:
        forms.alert(
            "The active view must be a Floor Plan or Structural Plan.\n"
            "Current view type: {}".format(active_view.ViewType),
            exitscript=True
        )
        return None
    
    return active_view


# ============================================
# Main Execution Flow
# ============================================
def main():
    """Main execution function"""
    try:
        # Get active view
        active_view = get_active_view()
        if active_view is None:
            return
        
        # Get user configuration
        config_data = get_config_ui(doc)
        if config_data is None:
            logger.warning("User cancelled configuration.")
            return

        selected_face = config_data['face']
        offset_distance = mm_to_internal(config_data['offset_mm'])
        selected_dimensioning_type = config_data['method']
        dim_type = config_data['dim_type']
        scope = config_data['scope']

        # Collect walls based on scope
        walls_to_process = None
        if scope == 'selection':
            walls_to_process = collect_walls_from_selection(doc)
            if not walls_to_process:
                forms.alert("No walls selected.", exitscript=True)
                return
        
        # Start Transaction Group for Preview support
        tg = DB.TransactionGroup(doc, "Auto Dimension Walls")
        tg.Start()

        try:
            # Start Revit transaction
            t = DB.Transaction(doc, "Create Dimensions")
            t.Start()
            
            try:
                dimensions_created, walls_processed = create_wall_dimensions(
                    doc,
                    active_view,
                    selected_face,
                    offset_distance,
                    selected_dimensioning_type,
                    dim_type,
                    walls_override=walls_to_process
                )
                t.Commit()
                
                # PREVIEW / CONFIRMATION
                uidoc.RefreshActiveView()
                
                msg = (
                    "Created {} dimensions on {} walls.\n\n"
                    "Accept changes?"
                ).format(dimensions_created, walls_processed)
                
                if forms.alert(msg, yes=True, no=True):
                    tg.Assimilate()
                else:
                    tg.RollBack()
                    logger.info("Operation cancelled by user (Preview Rejected).")

            except Exception as e:
                if t.HasStarted(): t.RollBack()
                tg.RollBack()
                logger.error("Transaction Error: {}".format(str(e)))
                forms.alert("Error: {}".format(str(e)))

        except Exception as e:
            if tg.HasStarted(): tg.RollBack()
            logger.error("Error: {}".format(str(e)))

    except Exception as e:
        import traceback
        logger.error(traceback.format_exc())
        forms.alert("Fatal Error: {}".format(str(e)))

if __name__ == "__main__":
    main()

