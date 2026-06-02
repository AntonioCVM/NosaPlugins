# -*- coding: utf-8 -*-
__title__ = "Add Piling"
__author__ = "Antonio Viñas"
__doc__ = """Places piles under a foundation slab (supports irregular shapes)
and automatically groups both piles and pile cap within a Model Group
automatically named as 'Core 1', 'Core 2', ...

IMPROVEMENTS v2.0:
✓ Integrated nosa_utils library
✓ Geometry caching for performance
✓ Preview grid before creation
✓ Persistent configuration (last spacing used)
✓ Better error handling and validation
"""

import clr
clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import *
from Autodesk.Revit import DB
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms, script

from System.Collections.Generic import List
import sys
import re
import math
import os

# Import NOSA utils library
extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
lib_path = os.path.join(extension_root, "lib")
if lib_path not in sys.path:
    sys.path.append(lib_path)
from nosa_utils import geometry, unit_conversion, ui_helpers, config_manager
from nosa_utils.revit_helpers import get_id_value

doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()

# Configuration
PILE_FAMILY_NAMES = ["Pile Square piling", "Pile-Steel Pipe Circular"]
ALLOWED_PILE_FAMILY_PREFIXES = ["pile square piling", "pile-steel pipe"]
DEFAULT_SPACING_MM = 1500
MIN_SPACING_MM = 300
MAX_SPACING_MM = 10000
DEFAULT_EMBEDMENT_MM = 75
MIN_EMBEDMENT_MM = 0
MAX_EMBEDMENT_MM = 3000

# Geometry cache for performance
_geometry_cache = {}

# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

config = config_manager.ConfigManager("add_pile_to_pilecap")

def save_last_config(spacing_mm, pile_type_name, embedment_mm):
    """Save last used configuration."""
    config.update({
        "last_spacing_mm": spacing_mm,
        "last_pile_type": pile_type_name,
        "last_embedment_mm": embedment_mm
    })

def load_last_config():
    """Load last used configuration."""
    return {
        "spacing_mm": config.get("last_spacing_mm", DEFAULT_SPACING_MM),
        "pile_type": config.get("last_pile_type", None),
        "embedment_mm": config.get("last_embedment_mm", DEFAULT_EMBEDMENT_MM)
    }

# =============================================================================
# SLAB SELECTION
# =============================================================================

class SlabFilter(ISelectionFilter):
    """Filter for selecting foundation slabs only."""
    def AllowElement(self, element):
        return element.Category and \
               get_id_value(element.Category.Id) == int(BuiltInCategory.OST_StructuralFoundation)
    def AllowReference(self, ref, point):
        return True

try:
    slab = doc.GetElement(
        uidoc.Selection.PickObject(
            ObjectType.Element,
            SlabFilter(),
            "Select a foundation slab"
        )
    )
except OperationCanceledException:
    forms.alert("Operation cancelled.", exitscript=True)
    raise

# =============================================================================
# SLAB LEVEL DETERMINATION
# =============================================================================

def get_slab_level(slab):
    """Get level associated with slab."""
    param = slab.get_Parameter(BuiltInParameter.LEVEL_PARAM)
    if param and param.StorageType == StorageType.ElementId:
        lvl = doc.GetElement(param.AsElementId())
        if lvl:
            return lvl
    
    param = slab.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
    if param and param.StorageType == StorageType.ElementId:
        lvl = doc.GetElement(param.AsElementId())
        if lvl:
            return lvl
    
    return None

level = get_slab_level(slab)
if not level:
    levels_list = list(FilteredElementCollector(doc).OfClass(Level))
    level_names = [n.Name for n in levels_list]
    idx = forms.SelectFromList.show(level_names, title="Select level for piles")
    if idx is None:
        forms.alert("No level selected.", exitscript=True)
    level = levels_list[level_names.index(idx)]

# =============================================================================
# GEOMETRY EXTRACTION (WITH CACHE)
# =============================================================================

def get_slab_solid_cached(element):
    """
    Get solid geometry with caching for performance.
    Uses nosa_utils.geometry module.
    """
    elem_id = get_id_value(element.Id)
    if elem_id in _geometry_cache:
        return _geometry_cache[elem_id]
    
    solid = geometry.get_solid_from_element(element)
    if solid:
        _geometry_cache[elem_id] = solid
    return solid

slab_solid = get_slab_solid_cached(slab)
if not slab_solid:
    forms.alert("Could not obtain slab geometry.", exitscript=True)

# =============================================================================
# BOTTOM FACE EXTRACTION
# =============================================================================

def bottom_face(solid):
    """Find the bottom face of a solid."""
    min_face = None
    min_z = None
    for face in solid.Faces:
        bbox_uv = face.GetBoundingBox()
        centre_uv = (bbox_uv.Min + bbox_uv.Max) / 2
        xyz_point = face.Evaluate(centre_uv)
        face_z = xyz_point.Z
        if min_z is None or face_z < min_z:
            min_z = face_z
            min_face = face
    return min_face, min_z

face_inf, min_z = bottom_face(slab_solid)
if not face_inf:
    forms.alert("Could not determine slab bottom face.", exitscript=True)

# =============================================================================
# EXTRACT CONTOUR POLYGONS (WITH TRANSFORM)
# =============================================================================

# Get the transform from the element to convert local coordinates to model coordinates
geometry_options = DB.Options()
geometry_options.ComputeReferences = True
geometry_options.IncludeNonVisibleObjects = True

def get_element_transform(element, options):
    """Get element transform if it exists (FamilyInstance, nested geometry, etc.)."""
    try:
        if hasattr(element, 'GetTransform'):
            t = element.GetTransform()
            if t:
                return t
    except Exception:
        pass
    
    try:
        geom_elem = element.get_Geometry(options)
        if geom_elem:
            for geo_obj in geom_elem:
                if hasattr(geo_obj, 'Transform') and geo_obj.Transform:
                    return geo_obj.Transform
    except Exception:
        pass
    
    return None

def get_polygons_bbox(polygons):
    """Get 2D bounding box for polygons."""
    try:
        min_x = min(pt[0] for poly in polygons for pt in poly)
        min_y = min(pt[1] for poly in polygons for pt in poly)
        max_x = max(pt[0] for poly in polygons for pt in poly)
        max_y = max(pt[1] for poly in polygons for pt in poly)
        return min_x, min_y, max_x, max_y
    except Exception:
        return None

def apply_transform_to_polygons(polygons, transform, z_value):
    """Apply a transform to polygon points."""
    new_polygons = []
    for poly in polygons:
        new_poly = []
        for x, y in poly:
            pt = XYZ(x, y, z_value)
            tpt = transform.OfPoint(pt)
            new_poly.append((tpt.X, tpt.Y))
        new_polygons.append(new_poly)
    return new_polygons

def translate_polygons(polygons, dx, dy):
    """Translate polygon points by dx, dy."""
    new_polygons = []
    for poly in polygons:
        new_poly = []
        for x, y in poly:
            new_poly.append((x + dx, y + dy))
        new_polygons.append(new_poly)
    return new_polygons

def get_project_location_inverse_transform():
    """Get inverse transform from shared to internal coordinates."""
    try:
        loc = doc.ActiveProjectLocation
        if loc:
            t = loc.GetTransform()
            if t:
                return t.Inverse
    except Exception:
        pass
    return None

def normalize_polygons_to_internal(polygons, element, transform=None):
    """Normalize polygon points to internal model coordinates."""
    if not polygons:
        return polygons
    
    # Apply element transform if provided and non-identity
    if transform and not (hasattr(transform, 'IsIdentity') and transform.IsIdentity):
        polygons = apply_transform_to_polygons(polygons, transform, 0.0)
    
    # Use element bounding box for reference
    try:
        elem_bbox = element.get_BoundingBox(None)
    except Exception:
        elem_bbox = None
    
    if not elem_bbox:
        return polygons
    
    poly_bbox = get_polygons_bbox(polygons)
    if not poly_bbox:
        return polygons
    
    poly_center_x = (poly_bbox[0] + poly_bbox[2]) / 2.0
    poly_center_y = (poly_bbox[1] + poly_bbox[3]) / 2.0
    
    elem_center_x = (elem_bbox.Min.X + elem_bbox.Max.X) / 2.0
    elem_center_y = (elem_bbox.Min.Y + elem_bbox.Max.Y) / 2.0
    
    elem_size_x = abs(elem_bbox.Max.X - elem_bbox.Min.X)
    elem_size_y = abs(elem_bbox.Max.Y - elem_bbox.Min.Y)
    threshold = max(elem_size_x, elem_size_y) * 2.0
    
    # If polygon center is far away, try project location inverse transform
    if abs(poly_center_x - elem_center_x) > threshold or abs(poly_center_y - elem_center_y) > threshold:
        inv_transform = get_project_location_inverse_transform()
        if inv_transform:
            polygons = apply_transform_to_polygons(polygons, inv_transform, 0.0)
            poly_bbox = get_polygons_bbox(polygons)
            if poly_bbox:
                poly_center_x = (poly_bbox[0] + poly_bbox[2]) / 2.0
                poly_center_y = (poly_bbox[1] + poly_bbox[3]) / 2.0
        
        # Final fallback: translate polygon to element center
        dx = elem_center_x - poly_center_x
        dy = elem_center_y - poly_center_y
        polygons = translate_polygons(polygons, dx, dy)
    
    return polygons

def get_outer_polygon(polygons):
    """Get the largest polygon by area."""
    if not polygons:
        return None
    if len(polygons) == 1:
        return polygons[0]
    
    max_area = -1
    outer_poly = polygons[0]
    for poly in polygons:
        area = geometry.calculate_polygon_area(poly)
        if area > max_area:
            max_area = area
            outer_poly = poly
    return outer_poly

def get_longest_edge_direction(poly):
    """Get direction of the longest edge in XY plane."""
    if not poly or len(poly) < 2:
        return XYZ.BasisX
    
    max_len = 0.0
    best_dir = XYZ.BasisX
    n = len(poly)
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length > max_len and length > 1e-9:
            max_len = length
            best_dir = XYZ(dx / length, dy / length, 0)
    
    return best_dir

def project_polygons_to_uv(polygons, origin, x_dir, y_dir):
    """Project world XY polygons into local UV coordinates."""
    uv_polygons = []
    for poly in polygons:
        uv_poly = []
        for x, y in poly:
            vec = XYZ(x - origin.X, y - origin.Y, 0)
            u = vec.DotProduct(x_dir)
            v = vec.DotProduct(y_dir)
            uv_poly.append((u, v))
        uv_polygons.append(uv_poly)
    return uv_polygons

def uv_to_world(u, v, origin, x_dir, y_dir, z_value):
    """Convert local UV to world XYZ."""
    return XYZ(
        origin.X + x_dir.X * u + y_dir.X * v,
        origin.Y + x_dir.Y * u + y_dir.Y * v,
        z_value
    )

def get_face_boundary_points(face):
    """Get boundary points from a face."""
    points = []
    try:
        if hasattr(face, "GetEdgesAsCurveLoops"):
            curve_loops = face.GetEdgesAsCurveLoops()
            for loop in curve_loops:
                for curve in loop:
                    try:
                        points.extend(curve.Tessellate())
                    except Exception:
                        try:
                            points.append(curve.GetEndPoint(0))
                            points.append(curve.GetEndPoint(1))
                        except Exception:
                            pass
    except Exception:
        pass
    return points

def get_longest_edge_direction_from_face(face):
    """Get direction of the longest edge on a face (XY projection)."""
    max_len = 0.0
    best_dir = XYZ.BasisX
    try:
        if hasattr(face, "GetEdgesAsCurveLoops"):
            curve_loops = face.GetEdgesAsCurveLoops()
            for loop in curve_loops:
                for curve in loop:
                    try:
                        length = curve.Length
                        if length > max_len:
                            start = curve.GetEndPoint(0)
                            end = curve.GetEndPoint(1)
                            dx = end.X - start.X
                            dy = end.Y - start.Y
                            lxy = math.sqrt(dx * dx + dy * dy)
                            if lxy > 1e-9:
                                max_len = length
                                best_dir = XYZ(dx / lxy, dy / lxy, 0)
                    except Exception:
                        pass
    except Exception:
        pass
    
    return best_dir

def project_points_to_uv(points, origin, x_dir, y_dir):
    """Project XYZ points into local UV coordinates."""
    uv_points = []
    for pt in points:
        vec = pt - origin
        u = vec.DotProduct(x_dir)
        v = vec.DotProduct(y_dir)
        uv_points.append((u, v))
    return uv_points

def point_in_face(face, point):
    """Check if a point lies inside a face boundary."""
    try:
        proj = face.Project(point)
        if proj and hasattr(face, "IsInside"):
            return face.IsInside(proj.UVPoint)
    except Exception:
        pass
    return False
    
    try:
        solid_bbox = solid.GetBoundingBox()
    except Exception:
        solid_bbox = None
    
    if not solid_bbox:
        return polygons
    
    poly_bbox = get_polygons_bbox(polygons)
    if not poly_bbox:
        return polygons
    
    poly_center_x = (poly_bbox[0] + poly_bbox[2]) / 2.0
    poly_center_y = (poly_bbox[1] + poly_bbox[3]) / 2.0
    
    solid_center_x = (solid_bbox.Min.X + solid_bbox.Max.X) / 2.0
    solid_center_y = (solid_bbox.Min.Y + solid_bbox.Max.Y) / 2.0
    
    solid_size_x = abs(solid_bbox.Max.X - solid_bbox.Min.X)
    solid_size_y = abs(solid_bbox.Max.Y - solid_bbox.Min.Y)
    threshold = max(solid_size_x, solid_size_y) * 2.0
    
    # If polygon center is far away, apply transform or translation
    if abs(poly_center_x - solid_center_x) > threshold or abs(poly_center_y - solid_center_y) > threshold:
        dx = solid_center_x - poly_center_x
        dy = solid_center_y - poly_center_y
        
        if transform and not (hasattr(transform, 'IsIdentity') and transform.IsIdentity):
            transformed = apply_transform_to_polygons(polygons, transform, z_value)
            transformed_bbox = get_polygons_bbox(transformed)
            if transformed_bbox:
                t_center_x = (transformed_bbox[0] + transformed_bbox[2]) / 2.0
                t_center_y = (transformed_bbox[1] + transformed_bbox[3]) / 2.0
                if abs(t_center_x - solid_center_x) > threshold or abs(t_center_y - solid_center_y) > threshold:
                    dx_t = solid_center_x - t_center_x
                    dy_t = solid_center_y - t_center_y
                    return translate_polygons(transformed, dx_t, dy_t)
            return transformed
        
        return translate_polygons(polygons, dx, dy)
    
    return polygons

transform = get_element_transform(slab, geometry_options)

def extract_contour_polygons(face, transform=None):
    """Extract exterior and hole polygons from face using robust methods.

    Args:
        face: PlanarFace from which to extract polygons
        transform: Transform to apply to points (converts from local to model coordinates)

    Returns:
        list: List of polygons as [(x,y), ...] in model coordinates
    """
    polygons = []
    
    # Method 1: GetEdgesAsCurveLoops (Best for PlanarFace)
    try:
        if hasattr(face, "GetEdgesAsCurveLoops"):
            curve_loops = face.GetEdgesAsCurveLoops()
            for loop in curve_loops:
                poly_pts = []
                # Process each curve in the valid loop
                for curve in loop:
                    # Use tessellation for accuracy with arcs
                    pts = curve.Tessellate()
                    # Skip the last point as it repeats start of next curve
                    for pt in pts[:-1]: 
                        # Apply transform if provided to get model coordinates
                        if transform:
                            pt = transform.OfPoint(pt)
                        poly_pts.append((pt.X, pt.Y))
                
                # Make sure to close the loop (add last point of last curve)
                if poly_pts:
                     polygons.append(poly_pts)
            return polygons
    except Exception as e:
        pass

    # Method 2: EdgeLoops (Fallback) - Requires Sorting
    try:
        for edge_array in face.EdgeLoops:
            # We must sort edges to form a continuous loop
            edges = [edge for edge in edge_array]
            if not edges:
                continue
                
            sorted_edges = []
            current_edge = edges.pop(0)
            sorted_edges.append(current_edge)
            
            # Simple greedy sort
            while edges:
                end_pt = current_edge.AsCurve().GetEndPoint(1)
                found_next = False
                for i, edge in enumerate(edges):
                    c = edge.AsCurve()
                    # Check start
                    if c.GetEndPoint(0).IsAlmostEqualTo(end_pt):
                        current_edge = edges.pop(i)
                        sorted_edges.append(current_edge)
                        found_next = True
                        break
                    # Check end (reverse)
                    elif c.GetEndPoint(1).IsAlmostEqualTo(end_pt):
                        current_edge = edges.pop(i)
                        sorted_edges.append(current_edge)
                        found_next = True
                        break
                
                if not found_next:
                    # Disconnected loop? Just pick next
                    if edges:
                        current_edge = edges.pop(0)
                        sorted_edges.append(current_edge)
            
            # Extract points from sorted edges
            poly_pts = []
            for edge in sorted_edges:
                pts = edge.Tessellate()
                for pt in pts[:-1]:
                    # Apply transform if provided to get model coordinates
                    if transform:
                        pt = transform.OfPoint(pt)
                    poly_pts.append((pt.X, pt.Y))
            
            if poly_pts:
                polygons.append(poly_pts)
                
    except Exception as e:
        # Final fallback: simple endpoint collection
        pass
        
    if not polygons:
        # Original simple method as last resort
        for edge_array in face.EdgeLoops:
            poly_pts = []
            for edge in edge_array:
                curve = edge.AsCurve()
                # Use tessellation for arcs
                pts = curve.Tessellate()
                for pt in pts[:-1]:
                    # Apply transform if provided to get model coordinates
                    if transform:
                        pt = transform.OfPoint(pt)
                    poly_pts.append((pt.X, pt.Y))
            if poly_pts:
                polygons.append(poly_pts)

    return polygons

polygons = extract_contour_polygons(face_inf)
polygons = normalize_polygons_to_internal(polygons, slab, transform)
if not polygons:
    forms.alert("Could not extract contour from slab.", exitscript=True)

# =============================================================================
# USER INPUT FOR SPACING
# =============================================================================

last_config = load_last_config()
default_spacing = last_config["spacing_mm"]
default_embedment = last_config["embedment_mm"]

spacing_mm = ui_helpers.ask_for_number(
    prompt="Enter pile spacing in millimeters:",
    default=default_spacing,
    min_value=MIN_SPACING_MM,
    max_value=MAX_SPACING_MM,
    title="Pile Spacing"
)

if spacing_mm is None:
    forms.alert("Operation cancelled.", exitscript=True)

spacing_ft = unit_conversion.mm_to_feet(spacing_mm)

# =============================================================================
# USER INPUT FOR EMBEDMENT
# =============================================================================

embedment_mm = ui_helpers.ask_for_number(
    prompt="Enter pile embedment in millimeters (distance from slab bottom to pile top):",
    default=default_embedment,
    min_value=MIN_EMBEDMENT_MM,
    max_value=MAX_EMBEDMENT_MM,
    title="Pile Embedment"
)

if embedment_mm is None:
    forms.alert("Operation cancelled.", exitscript=True)

embedment_ft = unit_conversion.mm_to_feet(embedment_mm)

# =============================================================================
# PILE TYPE SELECTION
# =============================================================================

def is_allowed_pile_family(family_name):
    """Check if family name is one of the allowed pile families."""
    name_lower = (family_name or "").strip().lower()
    for prefix in ALLOWED_PILE_FAMILY_PREFIXES:
        if name_lower.startswith(prefix):
            return True
    return False

def collect_pile_symbols():
    """Collect pile symbols from allowed structural foundation families."""
    symbols = []
    try:
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for sym in collector:
            try:
                cat = sym.Category
                if not cat:
                    continue
                if get_id_value(cat.Id) != int(BuiltInCategory.OST_StructuralFoundation):
                    continue
                
                family_name = sym.Family.Name if sym.Family else ""
                if is_allowed_pile_family(family_name):
                    symbols.append(sym)
            except Exception:
                continue
    except Exception as ex:
        output.print_md("⚠ Failed collecting pile symbols: {}".format(str(ex)))
    
    return symbols

all_pile_symbols = collect_pile_symbols()

if not all_pile_symbols:
    forms.alert(
        "No pile symbols found in the project.\n\n"
        "Allowed families:\n- Pile Square piling\n- Pile-Steel Pipe\n\n"
        "Load one of these families and try again.",
        exitscript=True
    )

def get_type_name(symbol):
    param = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
    return param.AsString() if param else "<No Type>"

def get_family_name(symbol):
    return symbol.Family.Name if symbol.Family else "<No Family>"

def symbol_sort_key(symbol):
    """Sort pile symbols with preferred families first, then by size."""
    family = get_family_name(symbol)
    priority = 1
    if family in PILE_FAMILY_NAMES:
        priority = 0
    name = get_type_name(symbol)
    numbers = re.findall(r'\d+', name)
    size = int(numbers[0]) if numbers else 0
    return (priority, family, size, name)

all_pile_symbols = sorted(all_pile_symbols, key=symbol_sort_key)

symbol_map = {}
pile_symbol_names = []
for sym in all_pile_symbols:
    name = "{} : {}".format(get_family_name(sym), get_type_name(sym))
    if name in symbol_map:
        name = "{} : {} [{}]".format(get_family_name(sym), get_type_name(sym), get_id_value(sym.Id))
    symbol_map[name] = sym
    pile_symbol_names.append(name)

# Pre-select last used pile type if available
default_index = None
last_pile_type = last_config.get("pile_type")
if last_pile_type:
    try:
        default_index = pile_symbol_names.index(last_pile_type)
    except ValueError:
        pass

selected_name = ui_helpers.ask_for_choice(
    pile_symbol_names,
    title="Select pile type",
    default=pile_symbol_names[default_index] if default_index is not None else None
)
if not selected_name:
    forms.alert("No pile type selected.", exitscript=True)

pile_symbol = symbol_map[selected_name]
selected_pile_name = selected_name

# Activate pile symbol if not active
if not pile_symbol.IsActive:
    with revit.Transaction("Activate Pile Symbol"):
        pile_symbol.Activate()

# Save configuration for next time
save_last_config(spacing_mm, selected_pile_name, embedment_mm)

# =============================================================================
# COMPUTE GRID POINTS ALIGNED WITH SLAB SPAN
# =============================================================================

# Get the ELEMENT's bounding box for XY coordinates
slab_bbox = slab.get_BoundingBox(None)
if not slab_bbox:
    forms.alert("Could not get slab bounding box.", exitscript=True)

# =============================================================================
# SLAB GEOMETRY - Use element parameters for accurate Z values
# =============================================================================
# The slab parameters "Elevation at Top" and "Elevation at Bottom" are the
# most accurate source for vertical positioning.

def get_slab_elevations(slab_element):
    """Get slab top and bottom elevations from parameters."""
    top_z = None
    bottom_z = None
    
    # Try STRUCTURAL_ELEVATION_AT_TOP / AT_BOTTOM (for structural floors)
    try:
        param_top = slab_element.get_Parameter(BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP)
        if param_top and param_top.HasValue:
            top_z = param_top.AsDouble()
        
        param_bot = slab_element.get_Parameter(BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM)
        if param_bot and param_bot.HasValue:
            bottom_z = param_bot.AsDouble()
    except Exception:
        pass
    
    # If not found, try searching by name
    if top_z is None or bottom_z is None:
        for param in slab_element.Parameters:
            name = param.Definition.Name.lower()
            if param.HasValue and param.StorageType == DB.StorageType.Double:
                if 'elevation at top' in name or 'elevacion superior' in name:
                    top_z = param.AsDouble()
                elif 'elevation at bottom' in name or 'elevacion inferior' in name:
                    bottom_z = param.AsDouble()
    
    return top_z, bottom_z

slab_top_z, slab_bottom_z = get_slab_elevations(slab)

# Fallback to BoundingBox if parameters not found
if slab_top_z is None:
    slab_top_z = slab_bbox.Max.Z
    print("WARNING: Using BoundingBox for slab top Z")
if slab_bottom_z is None:
    slab_bottom_z = slab_bbox.Min.Z
    print("WARNING: Using BoundingBox for slab bottom Z")

slab_thickness_ft = slab_top_z - slab_bottom_z

print("="*50)
print("SLAB VERTICAL GEOMETRY (from element parameters)")
print("="*50)
print("Slab Top (cara superior):    {:.3f} m  ({:.0f} mm)".format(
    slab_top_z * 0.3048, slab_top_z * 304.8))
print("Slab Bottom (cara inferior): {:.3f} m  ({:.0f} mm)".format(
    slab_bottom_z * 0.3048, slab_bottom_z * 304.8))
print("Slab Thickness (espesor):    {:.3f} m  ({:.0f} mm)".format(
    slab_thickness_ft * 0.3048, slab_thickness_ft * 304.8))

# slab_z is used for grid point generation (at bottom face)
slab_z = slab_bottom_z

# Extract edge vertices from bottom face to find span direction
def get_face_vertices(face):
    """Get all vertices from face edges."""
    vertices = []
    try:
        for edge_loop in face.EdgeLoops:
            for edge in edge_loop:
                curve = edge.AsCurve()
                vertices.append(curve.GetEndPoint(0))
    except Exception:
        pass
    return vertices

def find_longest_edge(face):
    """Find the longest edge of a face and return its direction."""
    longest_dir = XYZ.BasisX
    longest_length = 0
    try:
        for edge_loop in face.EdgeLoops:
            for edge in edge_loop:
                curve = edge.AsCurve()
                length = curve.Length
                if length > longest_length:
                    longest_length = length
                    start = curve.GetEndPoint(0)
                    end = curve.GetEndPoint(1)
                    longest_dir = (end - start).Normalize()
    except Exception:
        pass
    return longest_dir, longest_length

# Get span direction from bottom face
span_dir, span_length = find_longest_edge(face_inf)

# Calculate rotation angle from global X axis to span direction
# This will be used to rotate piles to align with slab span
import math
span_rotation_angle = math.atan2(span_dir.Y, span_dir.X)  # Radians

# Perpendicular direction (in XY plane)
perp_dir = XYZ(-span_dir.Y, span_dir.X, 0).Normalize()

# Get face vertices to compute center and dimensions
vertices = get_face_vertices(face_inf)
if not vertices:
    forms.alert("Could not extract slab vertices.", exitscript=True)

# Compute centroid of slab
center_x = sum(v.X for v in vertices) / len(vertices)
center_y = sum(v.Y for v in vertices) / len(vertices)
slab_center = XYZ(center_x, center_y, slab_z)

# Project vertices onto local axes to find dimensions
u_coords = []
v_coords = []
for v in vertices:
    vec = v - slab_center
    u = vec.X * span_dir.X + vec.Y * span_dir.Y
    vv = vec.X * perp_dir.X + vec.Y * perp_dir.Y
    u_coords.append(u)
    v_coords.append(vv)

u_min, u_max = min(u_coords), max(u_coords)
v_min, v_max = min(v_coords), max(v_coords)

slab_width = u_max - u_min  # Along span direction
slab_height = v_max - v_min  # Perpendicular to span

# =============================================================================
# PILE GRID CALCULATION - GUARANTEED MARGIN < SPACING
# =============================================================================
# 
# Algorithm:
# 1. Calculate number of spaces that fit in dimension
# 2. Ensure resulting margin is ALWAYS < spacing
# 3. Also ensure margin is not too small (min 10% of spacing)

def calculate_pile_distribution(dimension, spacing):
    """
    Calculate pile distribution ensuring margin < spacing.
    Optimized to MINIMIZE edge margin while keeping piles inside.
    Returns (n_spaces, margin)
    """
    # Start with maximum number of spaces that fit
    n_spaces = max(1, int(dimension / spacing))
    margin = (dimension - n_spaces * spacing) / 2.0
    
    # If margin >= spacing, add more spaces until margin < spacing
    while margin >= spacing and n_spaces < 1000:
        n_spaces += 1
        margin = (dimension - n_spaces * spacing) / 2.0
    
    # If margin is very large (>75% spacing), we can add one more space
    # This brings piles closer to the edge
    if margin > spacing * 0.75:
        test_margin = (dimension - (n_spaces + 1) * spacing) / 2.0
        if test_margin > spacing * 0.05:  # Only if we keep minimal margin
            n_spaces += 1
            margin = test_margin
    
    # Absolute minimum margin (5% spacing or 50mm, whichever is larger)
    min_margin_abs = max(spacing * 0.05, 50 / 304.8)  # 50mm in feet
    while margin < min_margin_abs and n_spaces > 1:
        n_spaces -= 1
        margin = (dimension - n_spaces * spacing) / 2.0
    
    return n_spaces, margin

print("="*50)
print("SLAB ALIGNED WITH SPAN")
print("="*50)
print("Span direction: ({:.3f}, {:.3f})".format(span_dir.X, span_dir.Y))
print("Slab center: ({:.2f}, {:.2f})".format(center_x, center_y))
print("Slab dimensions (aligned): {:.2f} x {:.2f} ft".format(slab_width, slab_height))
print("Spacing: {:.2f} ft ({:.0f} mm)".format(spacing_ft, spacing_ft * 304.8))

# Calculate optimal distribution
n_spaces_u_opt, margin_u_opt = calculate_pile_distribution(slab_width, spacing_ft)
n_spaces_v_opt, margin_v_opt = calculate_pile_distribution(slab_height, spacing_ft)

# =============================================================================
# GENERATE DISTRIBUTION OPTIONS FOR USER SELECTION
# =============================================================================
def generate_distribution_options(dim_u, dim_v, spacing, n_opt_u, n_opt_v):
    """
    Generate multiple distribution options around the optimal.
    Returns list of (n_u, n_v, margin_u, margin_v, description) tuples.
    """
    options = []
    min_margin = max(spacing * 0.05, 50 / 304.8)  # Minimum 50mm
    
    # Generate variations: -1, 0, +1 in each direction
    for delta_u in [-1, 0, 1]:
        for delta_v in [-1, 0, 1]:
            n_u = max(1, n_opt_u + delta_u)
            n_v = max(1, n_opt_v + delta_v)
            
            # Calculate margins
            margin_u = (dim_u - n_u * spacing) / 2.0
            margin_v = (dim_v - n_v * spacing) / 2.0
            
            # Skip invalid configurations (negative margins or too small)
            if margin_u < min_margin or margin_v < min_margin:
                continue
            
            # Skip if margin is too large (> spacing means we're missing a row)
            if margin_u > spacing * 1.2 or margin_v > spacing * 1.2:
                continue
            
            total = (n_u + 1) * (n_v + 1)
            options.append((n_u, n_v, margin_u, margin_v, total))
    
    # Remove duplicates and sort by total piles
    seen = set()
    unique_options = []
    for opt in options:
        key = (opt[0], opt[1])
        if key not in seen:
            seen.add(key)
            unique_options.append(opt)
    
    unique_options.sort(key=lambda x: x[4])  # Sort by total piles
    return unique_options

distribution_options = generate_distribution_options(
    slab_width, slab_height, spacing_ft, n_spaces_u_opt, n_spaces_v_opt
)

# Format options for display
option_strings = []
option_details = []
for i, (n_u, n_v, m_u, m_v, total) in enumerate(distribution_options):
    piles_u = n_u + 1
    piles_v = n_v + 1
    margin_u_mm = m_u * 304.8
    margin_v_mm = m_v * 304.8
    
    # Create display string
    opt_str = "Option {}: {} x {} = {} piles".format(i + 1, piles_u, piles_v, total)
    
    # Create detailed description
    detail = "{} x {} piles ({} total)\n".format(piles_u, piles_v, total)
    detail += "  Margin U (span):  {:.0f} mm\n".format(margin_u_mm)
    detail += "  Margin V (perp):  {:.0f} mm".format(margin_v_mm)
    
    option_strings.append(opt_str)
    option_details.append((n_u, n_v, m_u, m_v))

print("")
print("Distribution options generated: {}".format(len(option_strings)))
for opt in option_strings:
    print("  " + opt)

# Show selection dialog
if len(option_strings) > 1:
    # Find recommended option (closest to optimal)
    recommended_idx = 0
    for i, (n_u, n_v, m_u, m_v) in enumerate(option_details):
        if n_u == n_spaces_u_opt and n_v == n_spaces_v_opt:
            recommended_idx = i
            break
    
    # Mark recommended option
    marked_options = []
    for i, opt in enumerate(option_strings):
        if i == recommended_idx:
            marked_options.append(opt + " [RECOMENDADO]")
        else:
            marked_options.append(opt)
    
    selected_option = forms.SelectFromList.show(
        marked_options,
        title="Select Pile Distribution",
        button_name="Select",
        multiselect=False,
        default=marked_options[recommended_idx]
    )
    
    if not selected_option:
        forms.alert("No distribution option selected.", exitscript=True)
    
    # Find selected index
    selected_idx = 0
    for i, opt in enumerate(marked_options):
        if opt == selected_option:
            selected_idx = i
            break
    
    n_spaces_u, n_spaces_v, edge_margin_u, edge_margin_v = option_details[selected_idx]
else:
    # Only one option available
    n_spaces_u, n_spaces_v, edge_margin_u, edge_margin_v = option_details[0]

n_piles_u = n_spaces_u + 1
n_piles_v = n_spaces_v + 1

print("")
print("="*50)
print("SELECTED DISTRIBUTION")
print("="*50)
print("U direction (span):")
print("  Total piles: {} ({} spaces)".format(n_piles_u, n_spaces_u))
print("  Edge margin: {:.2f} ft ({:.0f} mm)".format(
    edge_margin_u, edge_margin_u * 304.8))
print("V direction (perp):")
print("  Total piles: {} ({} spaces)".format(n_piles_v, n_spaces_v))
print("  Edge margin: {:.2f} ft ({:.0f} mm)".format(
    edge_margin_v, edge_margin_v * 304.8))

# Store for later use
n_cols = n_spaces_u
n_rows = n_spaces_v
final_margin_u = edge_margin_u
final_margin_v = edge_margin_v

# For point-in-polygon check
min_edge_margin = min(edge_margin_u, edge_margin_v, spacing_ft * 0.15)

print("")
print("Total piles: {} x {} = {}".format(n_piles_u, n_piles_v, n_piles_u * n_piles_v))

# =============================================================================
# POINT-IN-POLYGON CHECK FOR IRREGULAR SLABS
# =============================================================================

def extract_face_boundary_points(face):
    """Extract boundary points from face edges as 2D polygon (XY only)."""
    boundary_points = []
    try:
        # Get the outer loop (first loop is typically the outer boundary)
        if face.EdgeLoops.Size > 0:
            outer_loop = face.EdgeLoops[0]
            for edge in outer_loop:
                curve = edge.AsCurve()
                pt = curve.GetEndPoint(0)
                boundary_points.append((pt.X, pt.Y))
    except Exception:
        pass
    return boundary_points

def point_in_polygon_2d(x, y, polygon):
    """
    Check if point (x,y) is inside polygon using ray casting algorithm.
    polygon is a list of (x, y) tuples.
    """
    if len(polygon) < 3:
        return False
    
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

def point_distance_to_polygon_edge(x, y, polygon):
    """Calculate minimum distance from point to polygon edges."""
    if len(polygon) < 2:
        return float('inf')
    
    min_dist = float('inf')
    n = len(polygon)
    
    for i in range(n):
        p1x, p1y = polygon[i]
        p2x, p2y = polygon[(i + 1) % n]
        
        # Vector from p1 to p2
        dx = p2x - p1x
        dy = p2y - p1y
        
        # Length squared
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            # p1 and p2 are the same point
            dist = math.sqrt((x - p1x)**2 + (y - p1y)**2)
        else:
            # Parameter t for closest point on line segment
            t = max(0, min(1, ((x - p1x) * dx + (y - p1y) * dy) / len_sq))
            
            # Closest point on segment
            closest_x = p1x + t * dx
            closest_y = p1y + t * dy
            
            dist = math.sqrt((x - closest_x)**2 + (y - closest_y)**2)
        
        min_dist = min(min_dist, dist)
    
    return min_dist

# Extract slab boundary as 2D polygon
slab_boundary_polygon = extract_face_boundary_points(face_inf)
print("Slab boundary points extracted: {}".format(len(slab_boundary_polygon)))

# Minimum distance from edge - Use smallest of calculated margins or 10% of spacing
# This allows piles to be close to edge but not ON the edge
# Minimum absolute value: 50mm
min_edge_abs = max(50 / 304.8, spacing_ft * 0.10)  # 50mm or 10% spacing
min_edge_distance = min(final_margin_u, final_margin_v, min_edge_abs)
min_edge_distance = max(min_edge_distance, 50 / 304.8)  # Never less than 50mm
print("Min distance to edge: {:.2f} ft ({:.0f} mm)".format(min_edge_distance, min_edge_distance * 304.8))

grid_points = []
points_rejected = 0

# =============================================================================
# DETERMINE SLAB TYPE: RECTANGULAR vs IRREGULAR
# =============================================================================
# Rectangular slabs (4 boundary points) use direct generation
# Irregular slabs use grid + filtering method

is_rectangular = len(slab_boundary_polygon) <= 6  # 4-6 points = rectangular/simple
print("")
if is_rectangular:
    print("Slab type: RECTANGULAR - Using direct grid generation")
else:
    print("Slab type: IRREGULAR ({} boundary points) - Using filtered grid".format(
        len(slab_boundary_polygon)))

# =============================================================================
# GENERATE GRID ALIGNED WITH SLAB SPAN
# =============================================================================

if is_rectangular:
    # =========================================================================
    # RECTANGULAR SLAB: Generate exact grid based on user selection
    # =========================================================================
    # For rectangular slabs, generate exactly n_piles_u x n_piles_v points
    # centered on the slab with the calculated margins
    
    print("Generating {} x {} = {} piles directly...".format(
        n_piles_u, n_piles_v, n_piles_u * n_piles_v))
    
    # Calculate start positions in local coordinates
    # Grid spans from -half_span to +half_span
    half_span_u = (n_spaces_u * spacing_ft) / 2.0
    half_span_v = (n_spaces_v * spacing_ft) / 2.0
    
    for iv in range(n_piles_v):
        for iu in range(n_piles_u):
            # Local coordinates centered on slab
            u_local = -half_span_u + iu * spacing_ft
            v_local = -half_span_v + iv * spacing_ft
            
            # Transform to global coordinates
            x_global = slab_center.X + u_local * span_dir.X + v_local * perp_dir.X
            y_global = slab_center.Y + u_local * span_dir.Y + v_local * perp_dir.Y
            
            pt = XYZ(x_global, y_global, slab_z)
            grid_points.append(pt)
    
    print("Grid points generated: {}".format(len(grid_points)))
    if grid_points:
        print("First point: X={:.2f}, Y={:.2f}, Z={:.2f}".format(
            grid_points[0].X, grid_points[0].Y, grid_points[0].Z))

else:
    # =========================================================================
    # IRREGULAR SLAB: Generate extended grid and filter
    # =========================================================================
    print("Generating filtered grid for irregular slab...")
    
    # Calculate bounding box in LOCAL coordinates (U-V system)
    local_u_coords = []
    local_v_coords = []
    for pt_x, pt_y in slab_boundary_polygon:
        dx = pt_x - slab_center.X
        dy = pt_y - slab_center.Y
        u = dx * span_dir.X + dy * span_dir.Y
        v = dx * perp_dir.X + dy * perp_dir.Y
        local_u_coords.append(u)
        local_v_coords.append(v)
    
    local_u_min = min(local_u_coords) if local_u_coords else -slab_width/2
    local_u_max = max(local_u_coords) if local_u_coords else slab_width/2
    local_v_min = min(local_v_coords) if local_v_coords else -slab_height/2
    local_v_max = max(local_v_coords) if local_v_coords else slab_height/2
    
    # Add margin
    margin_extra = spacing_ft * 0.5
    local_u_min -= margin_extra
    local_u_max += margin_extra
    local_v_min -= margin_extra
    local_v_max += margin_extra
    
    local_width = local_u_max - local_u_min
    local_height = local_v_max - local_v_min
    
    n_grid_u = int(local_width / spacing_ft) + 3
    n_grid_v = int(local_height / spacing_ft) + 3
    
    start_u = local_u_min + (local_width - (n_grid_u - 1) * spacing_ft) / 2.0
    start_v = local_v_min + (local_height - (n_grid_v - 1) * spacing_ft) / 2.0
    
    print("Local BBox (U-V): {:.1f} x {:.1f} ft".format(local_width, local_height))
    print("Grid size: {} x {} = {} positions".format(n_grid_u, n_grid_v, n_grid_u * n_grid_v))
    
    for iv in range(n_grid_v):
        for iu in range(n_grid_u):
            u_local = start_u + iu * spacing_ft
            v_local = start_v + iv * spacing_ft
            
            x_global = slab_center.X + u_local * span_dir.X + v_local * perp_dir.X
            y_global = slab_center.Y + u_local * span_dir.Y + v_local * perp_dir.Y
            
            # Check if point is inside slab with proper edge distance
            pt_valid = False
            edge_dist = None
            
            # Calculate edge distance if we have the polygon
            if slab_boundary_polygon and len(slab_boundary_polygon) >= 3:
                # First check if point is inside polygon
                if point_in_polygon_2d(x_global, y_global, slab_boundary_polygon):
                    edge_dist = point_distance_to_polygon_edge(x_global, y_global, slab_boundary_polygon)
                    
                    # Point is valid if distance to edge >= min_edge_distance
                    if edge_dist >= min_edge_distance:
                        pt_valid = True
            
            # Fallback to face projection if polygon method didn't find valid point
            if not pt_valid and face_inf:
                try:
                    test_pt = XYZ(x_global, y_global, slab_z)
                    result = face_inf.Project(test_pt)
                    if result:
                        uv = result.UVPoint
                        if face_inf.IsInside(uv):
                            # Verify projection didn't move point significantly
                            projected_pt = result.XYZPoint
                            xy_distance = math.sqrt((projected_pt.X - x_global)**2 + 
                                                   (projected_pt.Y - y_global)**2)
                            if xy_distance < 0.1:
                                # Check edge distance
                                if edge_dist is None and slab_boundary_polygon:
                                    edge_dist = point_distance_to_polygon_edge(x_global, y_global, slab_boundary_polygon)
                                if edge_dist is not None:
                                    if edge_dist >= min_edge_distance:
                                        pt_valid = True
                                else:
                                    pt_valid = True  # No polygon to check
                except Exception:
                    pass
            
            if pt_valid:
                grid_points.append(XYZ(x_global, y_global, slab_z))
            else:
                points_rejected += 1
    
    print("Grid points generated: {} (rejected: {} outside slab)".format(
        len(grid_points), points_rejected))
    if grid_points:
        print("First point: X={:.2f}, Y={:.2f}, Z={:.2f}".format(
            grid_points[0].X, grid_points[0].Y, grid_points[0].Z))

if not grid_points:
    # DEBUG DIAGNOSTICS
    print("\n" + "="*50)
    print("DEBUG DIAGNOSTICS - NO PILES FOUND")
    print("="*50)
    print("Slab dimensions (aligned): {:.2f} x {:.2f} ft".format(slab_width, slab_height))
    print("Grid Config: {} cols x {} rows, Spacing: {:.2f}ft".format(n_cols + 1, n_rows + 1, spacing_ft))
    print("Edge margins: U={:.2f}ft, V={:.2f}ft".format(final_margin_u, final_margin_v))

    forms.alert("No valid pile positions found within slab boundary.\n\nCheck the output window for debug details.", exitscript=True)

# =============================================================================
# PREVIEW CONFIRMATION
# =============================================================================

preview_message = """=== PILE PLACEMENT PREVIEW ===

Foundation Slab: {}

Pile Type: {}
Spacing: {} mm ({} ft)
Embedment: {} mm ({} ft)
Grid: {} columns x {} rows
Edge margin: {} mm
Total piles to create: {}

Proceed with pile creation?""".format(
    slab.Id,
    selected_pile_name,
    int(spacing_mm),
    round(spacing_ft, 3),
    int(embedment_mm),
    round(embedment_ft, 3),
    n_cols + 1,
    n_rows + 1,
    int(min(final_margin_u, final_margin_v) * 304.8),
    len(grid_points)
)

if not ui_helpers.confirm_action(preview_message, title="Confirm Pile Placement"):
    forms.alert("Operation cancelled by user.", exitscript=True)

# =============================================================================
# CREATE PILES
# =============================================================================

# Get pile height from the symbol to calculate correct insertion Z
def get_pile_height(symbol):
    """Get pile height from family symbol parameters."""
    height = None
    try:
        # Try FAMILY_HEIGHT_PARAM
        h_param = symbol.get_Parameter(BuiltInParameter.FAMILY_HEIGHT_PARAM)
        if h_param and h_param.HasValue:
            height = h_param.AsDouble()
            return height
        
        # Try other common height parameters
        for param in symbol.Parameters:
            name = param.Definition.Name.lower()
            if ('height' in name or 'length' in name or 'depth' in name) and param.HasValue:
                if param.StorageType == DB.StorageType.Double:
                    val = param.AsDouble()
                    if val > 1.0:  # More than 1 ft - likely the height
                        height = val
                        break
    except Exception:
        pass
    return height

pile_height_ft = get_pile_height(pile_symbol)
if pile_height_ft:
    print("Pile height: {:.3f} m ({:.0f} mm)".format(pile_height_ft * 0.3048, pile_height_ft * 304.8))
else:
    print("Could not determine pile height from symbol")

# =============================================================================
# PILE TOP Z CALCULATION
# =============================================================================
# Formula: Pile Top Z = Slab Bottom Z + Embedment
#
# Equivalent to: Slab Top - Thickness + Embedment = Pile Top Z
#
# Example:
#   Slab Top:     +1.575 m
#   Thickness:     2.000 m
#   Slab Bottom:  -0.425 m
#   Embedment:    +0.075 m
#   Pile Top:     -0.350 m

pile_top_z = slab_bottom_z + embedment_ft

print("")
print("="*50)
print("PILE INSERTION CALCULATION")
print("="*50)
print("Formula: Pile Top = Slab Bottom + Embedment")
print("")
print("  Slab Top (cara superior):    {:.3f} m".format(slab_top_z * 0.3048))
print("- Thickness (espesor):         {:.3f} m".format(slab_thickness_ft * 0.3048))
print("= Slab Bottom (cara inferior): {:.3f} m".format(slab_bottom_z * 0.3048))
print("+ Embedment:                   {:.3f} m".format(embedment_ft * 0.3048))
print("-" * 45)
print("= PILE TOP Z:                  {:.3f} m".format(pile_top_z * 0.3048))

# Calculate pile base Z (insertion point for Revit)
if pile_height_ft:
    pile_base_z = pile_top_z - pile_height_ft
    print("")
    print("Pile height:                   {:.3f} m".format(pile_height_ft * 0.3048))
    print("Pile Base Z (insertion):       {:.3f} m".format(pile_base_z * 0.3048))
else:
    # Fallback: use slab bottom and let Revit handle pile height
    pile_base_z = slab_bottom_z
    print("")
    print("WARNING: Could not get pile height. Using slab bottom as reference.")

output.print_md("## Creating Piles")
output.print_md("- **Pile Type:** {}".format(selected_pile_name))
output.print_md("- **Spacing:** {} mm".format(int(spacing_mm)))
output.print_md("- **Embedment:** {} mm".format(int(embedment_mm)))
output.print_md("- **Total Piles:** {}".format(len(grid_points)))
output.print_md("")

pile_ids = []
slab_id = slab.Id

# Import JoinGeometryUtils for unjoining elements
from Autodesk.Revit.DB import JoinGeometryUtils

# Print level info for debugging
print("")
print("Level used for piles: {} (Elevation: {:.3f} m = {:.0f} mm)".format(
    level.Name, level.Elevation * 0.3048, level.Elevation * 304.8))

with revit.Transaction("Create Piles"):
    for i, pt in enumerate(grid_points, 1):
        try:
            # STEP 1: Create pile at a reference point (level elevation)
            # We'll move it to the correct position after creation
            insertion_point = XYZ(pt.X, pt.Y, level.Elevation)
            pile_instance = doc.Create.NewFamilyInstance(
                insertion_point, pile_symbol, level, DB.Structure.StructuralType.Footing
            )
            pile_ids.append(pile_instance.Id)
            
            # STEP 2: Get the current Elevation at Top of the pile
            current_top_z = None
            try:
                param_top = pile_instance.get_Parameter(BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP)
                if param_top and param_top.HasValue:
                    current_top_z = param_top.AsDouble()
            except Exception:
                pass
            
            # If parameter not available, try by name
            if current_top_z is None:
                try:
                    for param in pile_instance.Parameters:
                        if 'Elevation at Top' in param.Definition.Name:
                            if param.HasValue and param.StorageType == DB.StorageType.Double:
                                current_top_z = param.AsDouble()
                                break
                except Exception:
                    pass
            
            # Fallback: estimate from bounding box
            if current_top_z is None:
                try:
                    doc.Regenerate()  # Force update
                    pile_bbox = pile_instance.get_BoundingBox(None)
                    if pile_bbox:
                        current_top_z = pile_bbox.Max.Z
                except Exception:
                    pass
            
            # STEP 3: Calculate and apply vertical movement
            if current_top_z is not None:
                # Move pile so its top is at pile_top_z
                z_move = pile_top_z - current_top_z
                
                if abs(z_move) > 0.001:  # Only move if needed (tolerance ~0.3mm)
                    move_vector = XYZ(0, 0, z_move)
                    DB.ElementTransformUtils.MoveElement(doc, pile_instance.Id, move_vector)
                
                if i == 1:
                    print("")
                    print("First pile positioning (MOVE method):")
                    print("  Current Top Z (after creation): {:.3f} m ({:.0f} mm)".format(
                        current_top_z * 0.3048, current_top_z * 304.8))
                    print("  Target Top Z:                   {:.3f} m ({:.0f} mm)".format(
                        pile_top_z * 0.3048, pile_top_z * 304.8))
                    print("  Z movement applied:             {:.3f} m ({:.0f} mm)".format(
                        z_move * 0.3048, z_move * 304.8))
            else:
                # Fallback: try to set Height Offset From Level
                height_offset_needed = pile_top_z - level.Elevation
                try:
                    for param in pile_instance.Parameters:
                        pname = param.Definition.Name
                        if 'Height Offset' in pname or 'Offset From Level' in pname:
                            if not param.IsReadOnly and param.StorageType == DB.StorageType.Double:
                                param.Set(height_offset_needed)
                                if i == 1:
                                    print("Fallback: Set Height Offset to {:.3f} m".format(
                                        height_offset_needed * 0.3048))
                                break
                except Exception:
                    pass
            
            # STEP 4: Unjoin pile from slab to prevent automatic joining
            try:
                if JoinGeometryUtils.AreElementsJoined(doc, pile_instance, slab):
                    JoinGeometryUtils.UnjoinGeometry(doc, pile_instance, slab)
            except Exception:
                pass  # May fail if elements are not joined
            
            # STEP 5: Rotate pile to align with slab span direction
            if abs(span_rotation_angle) > 0.001:  # Only rotate if angle is significant
                try:
                    # Get pile center point for rotation axis
                    pile_location = pile_instance.Location
                    if pile_location and hasattr(pile_location, 'Point'):
                        pile_center = pile_location.Point
                    else:
                        # Fallback: use insertion point
                        pile_center = XYZ(pt.X, pt.Y, pile_top_z)
                    
                    # Create vertical axis through pile center
                    axis_start = XYZ(pile_center.X, pile_center.Y, pile_center.Z - 1)
                    axis_end = XYZ(pile_center.X, pile_center.Y, pile_center.Z + 1)
                    rotation_axis = DB.Line.CreateBound(axis_start, axis_end)
                    
                    # Rotate pile around vertical axis
                    DB.ElementTransformUtils.RotateElement(
                        doc, pile_instance.Id, rotation_axis, span_rotation_angle
                    )
                    
                    if i == 1:
                        print("  Rotation applied:               {:.1f} degrees".format(
                            math.degrees(span_rotation_angle)))
                except Exception as rot_ex:
                    if i == 1:
                        print("  Rotation failed: {}".format(str(rot_ex)))
            
            # Progress reporting
            if i % 10 == 0 or i == len(grid_points):
                ui_helpers.show_progress(i, len(grid_points), "Creating piles")
        
        except Exception as e:
            output.print_md("⚠️ **Warning:** Failed to create pile at {}: {}".format(pt, str(e)))

if not pile_ids:
    forms.alert("No piles were created.", exitscript=True)

output.print_md("✓ {} piles created successfully".format(len(pile_ids)))

# =============================================================================
# UNJOIN ALL PILES FROM SLAB
# =============================================================================
# Ensure all piles are unjoined from the slab before grouping

output.print_md("")
output.print_md("## Unjoining Piles from Slab")

unjoin_count = 0
with revit.Transaction("Unjoin Piles from Slab"):
    for pile_id in pile_ids:
        try:
            pile_elem = doc.GetElement(pile_id)
            if pile_elem and JoinGeometryUtils.AreElementsJoined(doc, pile_elem, slab):
                JoinGeometryUtils.UnjoinGeometry(doc, pile_elem, slab)
                unjoin_count += 1
        except Exception:
            pass

output.print_md("✓ {} piles unjoined from slab".format(unjoin_count))

# =============================================================================
# CREATE GROUP
# =============================================================================

output.print_md("")
output.print_md("## Creating Model Group")

def find_next_core_number():
    """Find the next available 'Core N' number."""
    all_groups = FilteredElementCollector(doc).OfClass(Group).ToElements()
    pattern = re.compile(r'^Core (\d+)$', re.IGNORECASE)
    max_num = 0
    for g in all_groups:
        name = g.Name if hasattr(g, 'Name') else g.GroupType.Name
        m = pattern.match(name)
        if m:
            num = int(m.group(1))
            if num > max_num:
                max_num = num
    return max_num + 1

next_num = find_next_core_number()
group_name = "Core {}".format(next_num)

all_element_ids = List[ElementId]()
all_element_ids.Add(slab_id)
for pid in pile_ids:
    all_element_ids.Add(pid)

with revit.Transaction("Create Group '{}'".format(group_name)):
    try:
        new_group = doc.Create.NewGroup(all_element_ids)
        group_type = new_group.GroupType
        group_type.Name = group_name
        output.print_md("✓ Created group: **{}**".format(group_name))
        output.print_md("  - Contains: {} piles + 1 slab".format(len(pile_ids)))
    except Exception as e:
        output.print_md("⚠️ **Warning:** Could not create group: {}".format(str(e)))

# =============================================================================
# SUMMARY
# =============================================================================

output.print_md("")
output.print_md("---")
output.print_md("## ✅ Operation Complete")
ui_helpers.display_results("Final Results", {
    "Piles Created": len(pile_ids),
    "Slab ID": get_id_value(slab_id),
    "Group Name": group_name,
    "Spacing (mm)": int(spacing_mm)
})

output.print_md("")
output.print_md("*Configuration saved for next use*")
