# -*- coding: utf-8 -*-
import math
import os
import re
import sys

from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
from System.Collections.Generic import List

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import geometry, config_manager
from nosa_utils.revit_helpers import get_id_value

# Configuration
PILE_FAMILY_NAMES = ["Pile Square piling", "Pile-Steel Pipe Circular"]
ALLOWED_PILE_FAMILY_PREFIXES = ["pile square piling", "pile-steel pipe"]
DEFAULT_SPACING_MM = 1500
MIN_SPACING_MM = 300
MAX_SPACING_MM = 10000
DEFAULT_EMBEDMENT_MM = 75
MIN_EMBEDMENT_MM = 0
MAX_EMBEDMENT_MM = 3000
DEFAULT_CLEARANCE_MM = 150
MIN_CLEARANCE_MM = 0
MAX_CLEARANCE_MM = 2000

# Geometry cache for performance
_geometry_cache = {}

# =============================================================================
# CONFIGURATION MANAGEMENT
# =============================================================================

config = config_manager.ConfigManager("add_pile_to_pilecap")

def save_last_config(spacing_mm, pile_type_name, embedment_mm, clearance_mm=None):
    """Save last used configuration."""
    data = {
        "last_spacing_mm": spacing_mm,
        "last_pile_type": pile_type_name,
        "last_embedment_mm": embedment_mm
    }
    if clearance_mm is not None:
        data["last_clearance_mm"] = clearance_mm
    config.update(data)

def load_last_config():
    """Load last used configuration."""
    return {
        "spacing_mm": config.get("last_spacing_mm", DEFAULT_SPACING_MM),
        "pile_type": config.get("last_pile_type", None),
        "embedment_mm": config.get("last_embedment_mm", DEFAULT_EMBEDMENT_MM),
        "clearance_mm": config.get("last_clearance_mm", DEFAULT_CLEARANCE_MM)
    }
def generate_triangular_grid(slab_center, span_dir, perp_dir, slab_z,
                               spacing_ft, slab_width, slab_height,
                               slab_boundary_polygon, face_inf, min_edge_distance):
    """
    Triangular / staggered grid: even rows are a normal grid, odd rows
    are offset by spacing/2 in the U direction.
    Row spacing in V is spacing × sin(60°) ≈ 0.866 × spacing.
    """
    row_v_ft = spacing_ft * 0.8660254   # sin(60°)
    pts = []

    n_rows = int(slab_height / row_v_ft) + 2
    n_cols = int(slab_width  / spacing_ft) + 2

    half_u = (n_cols * spacing_ft) / 2.0
    half_v = (n_rows * row_v_ft)   / 2.0

    for ir in range(n_rows + 1):
        v_local = -half_v + ir * row_v_ft
        offset_u = (spacing_ft / 2.0) if (ir % 2 == 1) else 0.0
        for ic in range(n_cols + 1):
            u_local = -half_u + ic * spacing_ft + offset_u
            x_g = slab_center.X + u_local * span_dir.X + v_local * perp_dir.X
            y_g = slab_center.Y + u_local * span_dir.Y + v_local * perp_dir.Y
            if point_inside_check(x_g, y_g, slab_z, slab_boundary_polygon, face_inf, min_edge_distance):
                pts.append(DB.XYZ(x_g, y_g, slab_z))
    return pts


def generate_hexagonal_grid(slab_center, span_dir, perp_dir, slab_z,
                              spacing_ft, slab_width, slab_height,
                              slab_boundary_polygon, face_inf, min_edge_distance):
    """
    True hexagonal close-packed: alternating rows offset by spacing/2,
    row spacing = spacing × sqrt(3)/2.
    Identical to triangular but with V spacing = spacing × 0.866.
    """
    return generate_triangular_grid(
        slab_center, span_dir, perp_dir, slab_z,
        spacing_ft, slab_width, slab_height,
        slab_boundary_polygon, face_inf, min_edge_distance,
    )

def point_inside_check(x_g, y_g, slab_z, slab_boundary_polygon, face_inf, min_edge_distance):
    """Return True if point is inside the slab boundary with minimum edge clearance."""
    if slab_boundary_polygon and len(slab_boundary_polygon) >= 3:
        if point_in_polygon_2d(x_g, y_g, slab_boundary_polygon):
            d = point_distance_to_polygon_edge(x_g, y_g, slab_boundary_polygon)
            return d >= min_edge_distance
        return False
    # Fallback: face projection
    if face_inf:
        try:
            res = face_inf.Project(DB.XYZ(x_g, y_g, slab_z))
            if res:
                return face_inf.IsInside(res.UVPoint)
        except Exception:
            pass
    return True   # accept if no boundary data

class SlabFilter(ISelectionFilter):
    """Filter for selecting foundation slabs only."""
    def AllowElement(self, element):
        return element.Category and \
               get_id_value(element.Category.Id) == int(DB.BuiltInCategory.OST_StructuralFoundation)
    def AllowReference(self, ref, point):
        return True
def get_slab_level(doc, slab):
    """Get level associated with slab."""
    param = slab.get_Parameter(DB.BuiltInParameter.LEVEL_PARAM)
    if param and param.StorageType == DB.StorageType.ElementId:
        lvl = doc.GetElement(param.AsElementId())
        if lvl:
            return lvl
    
    param = slab.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)
    if param and param.StorageType == DB.StorageType.ElementId:
        lvl = doc.GetElement(param.AsElementId())
        if lvl:
            return lvl
    
    return None
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

# =============================================================================
# EXTRACT CONTOUR POLYGONS (WITH TRANSFORM)
# =============================================================================



def get_geometry_options():
    options = DB.Options()
    options.ComputeReferences = True
    options.IncludeNonVisibleObjects = True
    return options

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
            pt = DB.XYZ(x, y, z_value)
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

def get_project_location_inverse_transform(doc):
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

def normalize_polygons_to_internal(doc, polygons, element, transform=None):
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
        inv_transform = get_project_location_inverse_transform(doc)
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
        return DB.XYZ.BasisX
    
    max_len = 0.0
    best_dir = DB.XYZ.BasisX
    n = len(poly)
    for i in range(n):
        p1 = poly[i]
        p2 = poly[(i + 1) % n]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.sqrt(dx * dx + dy * dy)
        if length > max_len and length > 1e-9:
            max_len = length
            best_dir = DB.XYZ(dx / length, dy / length, 0)
    
    return best_dir

def project_polygons_to_uv(polygons, origin, x_dir, y_dir):
    """Project world XY polygons into local UV coordinates."""
    uv_polygons = []
    for poly in polygons:
        uv_poly = []
        for x, y in poly:
            vec = DB.XYZ(x - origin.X, y - origin.Y, 0)
            u = vec.DotProduct(x_dir)
            v = vec.DotProduct(y_dir)
            uv_poly.append((u, v))
        uv_polygons.append(uv_poly)
    return uv_polygons

def uv_to_world(u, v, origin, x_dir, y_dir, z_value):
    """Convert local UV to world XYZ."""
    return DB.XYZ(
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
    best_dir = DB.XYZ.BasisX
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
                                best_dir = DB.XYZ(dx / lxy, dy / lxy, 0)
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
def is_allowed_pile_family(family_name):
    """Check if family name is one of the allowed pile families."""
    name_lower = (family_name or "").strip().lower()
    for prefix in ALLOWED_PILE_FAMILY_PREFIXES:
        if name_lower.startswith(prefix):
            return True
    return False

def collect_pile_symbols(doc, log_fn=None):
    """Collect pile symbols from allowed structural foundation families."""
    symbols = []
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)
        for sym in collector:
            try:
                cat = sym.Category
                if not cat:
                    continue
                if get_id_value(cat.Id) != int(DB.BuiltInCategory.OST_StructuralFoundation):
                    continue
                
                family_name = sym.Family.Name if sym.Family else ""
                if is_allowed_pile_family(family_name):
                    symbols.append(sym)
            except Exception:
                continue
    except Exception as ex:
        if log_fn:
            log_fn("⚠ Failed collecting pile symbols: {}".format(str(ex)))
    
    return symbols

def get_type_name(symbol):
    param = symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
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
def get_slab_elevations(slab_element):
    """Get slab top and bottom elevations from parameters."""
    top_z = None
    bottom_z = None
    
    # Try STRUCTURAL_ELEVATION_AT_TOP / AT_BOTTOM (for structural floors)
    try:
        param_top = slab_element.get_Parameter(DB.BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP)
        if param_top and param_top.HasValue:
            top_z = param_top.AsDouble()
        
        param_bot = slab_element.get_Parameter(DB.BuiltInParameter.STRUCTURAL_ELEVATION_AT_BOTTOM)
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
    longest_dir = DB.XYZ.BasisX
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
def get_pile_height(symbol):
    """Get pile height from family symbol parameters."""
    height = None
    try:
        # Try FAMILY_HEIGHT_PARAM
        h_param = symbol.get_Parameter(DB.BuiltInParameter.FAMILY_HEIGHT_PARAM)
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

def generate_manual_grid(uidoc, slab_z):
    pts = []
    count = 0
    while True:
        try:
            picked = uidoc.Selection.PickPoint(
                u'Click pile position {} (press Esc to finish)'.format(count + 1))
            pt = DB.XYZ(picked.X, picked.Y, slab_z)
            pts.append(pt)
            count += 1
        except OperationCanceledException:
            break
        except Exception:
            break
    return pts


def generate_rectangular_grid(slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                              n_piles_u, n_piles_v, n_spaces_u, n_spaces_v):
    grid_points = []
    half_span_u = (n_spaces_u * spacing_ft) / 2.0
    half_span_v = (n_spaces_v * spacing_ft) / 2.0
    for iv in range(n_piles_v):
        for iu in range(n_piles_u):
            u_local = -half_span_u + iu * spacing_ft
            v_local = -half_span_v + iv * spacing_ft
            x_global = slab_center.X + u_local * span_dir.X + v_local * perp_dir.X
            y_global = slab_center.Y + u_local * span_dir.Y + v_local * perp_dir.Y
            grid_points.append(DB.XYZ(x_global, y_global, slab_z))
    return grid_points


def generate_irregular_grid(slab_center, span_dir, perp_dir, slab_z, spacing_ft,
                            slab_width, slab_height, slab_boundary_polygon, face_inf,
                            min_edge_distance):
    grid_points = []
    points_rejected = 0
    local_u_coords = []
    local_v_coords = []
    for pt_x, pt_y in slab_boundary_polygon:
        dx = pt_x - slab_center.X
        dy = pt_y - slab_center.Y
        u = dx * span_dir.X + dy * span_dir.Y
        v = dx * perp_dir.X + dy * perp_dir.Y
        local_u_coords.append(u)
        local_v_coords.append(v)
    local_u_min = min(local_u_coords) if local_u_coords else -slab_width / 2
    local_u_max = max(local_u_coords) if local_u_coords else slab_width / 2
    local_v_min = min(local_v_coords) if local_v_coords else -slab_height / 2
    local_v_max = max(local_v_coords) if local_v_coords else slab_height / 2
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

    print('Local BBox (U-V): {:.1f} x {:.1f} ft'.format(local_width, local_height))
    print('Grid size: {} x {} = {} positions'.format(n_grid_u, n_grid_v, n_grid_u * n_grid_v))

    for iv in range(n_grid_v):
        for iu in range(n_grid_u):
            u_local = start_u + iu * spacing_ft
            v_local = start_v + iv * spacing_ft
            x_global = slab_center.X + u_local * span_dir.X + v_local * perp_dir.X
            y_global = slab_center.Y + u_local * span_dir.Y + v_local * perp_dir.Y
            pt_valid = False
            edge_dist = None
            if slab_boundary_polygon and len(slab_boundary_polygon) >= 3:
                if point_in_polygon_2d(x_global, y_global, slab_boundary_polygon):
                    edge_dist = point_distance_to_polygon_edge(
                        x_global, y_global, slab_boundary_polygon)
                    if edge_dist >= min_edge_distance:
                        pt_valid = True
            if not pt_valid and face_inf:
                try:
                    test_pt = DB.XYZ(x_global, y_global, slab_z)
                    result = face_inf.Project(test_pt)
                    if result:
                        uv = result.UVPoint
                        if face_inf.IsInside(uv):
                            projected_pt = result.XYZPoint
                            xy_distance = math.sqrt(
                                (projected_pt.X - x_global) ** 2 +
                                (projected_pt.Y - y_global) ** 2)
                            if xy_distance < 0.1:
                                if edge_dist is None and slab_boundary_polygon:
                                    edge_dist = point_distance_to_polygon_edge(
                                        x_global, y_global, slab_boundary_polygon)
                                if edge_dist is not None:
                                    if edge_dist >= min_edge_distance:
                                        pt_valid = True
                                else:
                                    pt_valid = True
                except Exception:
                    pass
            if pt_valid:
                grid_points.append(DB.XYZ(x_global, y_global, slab_z))
            else:
                points_rejected += 1
    return grid_points, points_rejected


def apply_pattern_grid(pattern, uidoc, slab_center, span_dir, perp_dir, slab_z,
                       spacing_ft, slab_width, slab_height, slab_boundary_polygon,
                       face_inf, min_edge_distance, grid_points):
    if pattern == 'triangular':
        return generate_triangular_grid(
            slab_center, span_dir, perp_dir, slab_z,
            spacing_ft, slab_width, slab_height,
            slab_boundary_polygon, face_inf, min_edge_distance)
    if pattern == 'hexagonal':
        return generate_hexagonal_grid(
            slab_center, span_dir, perp_dir, slab_z,
            spacing_ft, slab_width, slab_height,
            slab_boundary_polygon, face_inf, min_edge_distance)
    if pattern == 'manual':
        return generate_manual_grid(uidoc, slab_z)
    return grid_points


def create_pile_at_point(doc, pt, pile_symbol, level, slab, pile_top_z, span_rotation_angle):
    from Autodesk.Revit.DB import JoinGeometryUtils
    insertion_point = DB.XYZ(pt.X, pt.Y, level.Elevation)
    try:
        from Autodesk.Revit.DB.Structure import StructuralType
        pile_instance = doc.Create.NewFamilyInstance(
            insertion_point, pile_symbol, level, StructuralType.Footing)
    except Exception:
        pile_instance = doc.Create.NewFamilyInstance(
            insertion_point, pile_symbol, level, DB.Structure.StructuralType.Footing)

    # Elevation-derived parameters (Elevation at Top, bounding box) are not
    # guaranteed accurate until the document regenerates after element
    # creation — reading them beforehand can silently return a stale/
    # default value that "looks" valid (HasValue=True) but doesn't reflect
    # where the pile actually is, making the embedment adjustment below
    # compute against the wrong baseline. Regenerate first so every
    # detection method below reads the pile's true as-created position.
    try:
        doc.Regenerate()
    except Exception:
        pass

    current_top_z = None
    try:
        param_top = pile_instance.get_Parameter(DB.BuiltInParameter.STRUCTURAL_ELEVATION_AT_TOP)
        if param_top and param_top.HasValue:
            current_top_z = param_top.AsDouble()
    except Exception:
        pass
    if current_top_z is None:
        try:
            for param in pile_instance.Parameters:
                if 'Elevation at Top' in param.Definition.Name:
                    if param.HasValue and param.StorageType == DB.StorageType.Double:
                        current_top_z = param.AsDouble()
                        break
        except Exception:
            pass
    if current_top_z is None:
        try:
            pile_bbox = pile_instance.get_BoundingBox(None)
            if pile_bbox:
                current_top_z = pile_bbox.Max.Z
        except Exception:
            pass
    z_move = 0.0
    if current_top_z is not None:
        z_move = pile_top_z - current_top_z
        if abs(z_move) > 0.001:
            move_vector = DB.XYZ(0, 0, z_move)
            DB.ElementTransformUtils.MoveElement(doc, pile_instance.Id, move_vector)
    else:
        height_offset_needed = pile_top_z - level.Elevation
        try:
            for param in pile_instance.Parameters:
                pname = param.Definition.Name
                if 'Height Offset' in pname or 'Offset From Level' in pname:
                    if not param.IsReadOnly and param.StorageType == DB.StorageType.Double:
                        param.Set(height_offset_needed)
                        break
        except Exception:
            pass
    try:
        if JoinGeometryUtils.AreElementsJoined(doc, pile_instance, slab):
            JoinGeometryUtils.UnjoinGeometry(doc, pile_instance, slab)
    except Exception:
        pass
    if abs(span_rotation_angle) > 0.001:
        try:
            pile_location = pile_instance.Location
            if pile_location and hasattr(pile_location, 'Point'):
                pile_center = pile_location.Point
            else:
                pile_center = DB.XYZ(pt.X, pt.Y, pile_top_z)
            axis_start = DB.XYZ(pile_center.X, pile_center.Y, pile_center.Z - 1)
            axis_end = DB.XYZ(pile_center.X, pile_center.Y, pile_center.Z + 1)
            rotation_axis = DB.Line.CreateBound(axis_start, axis_end)
            DB.ElementTransformUtils.RotateElement(
                doc, pile_instance.Id, rotation_axis, span_rotation_angle)
        except Exception:
            pass
    return pile_instance, current_top_z, z_move


def unjoin_piles_from_slab(doc, pile_ids, slab):
    from Autodesk.Revit.DB import JoinGeometryUtils
    count = 0
    for pile_id in pile_ids:
        try:
            pile_elem = doc.GetElement(pile_id)
            if pile_elem and JoinGeometryUtils.AreElementsJoined(doc, pile_elem, slab):
                JoinGeometryUtils.UnjoinGeometry(doc, pile_elem, slab)
                count += 1
        except Exception:
            pass
    return count


def create_core_group(doc, slab_id, pile_ids, group_name):
    all_element_ids = List[DB.ElementId]()
    all_element_ids.Add(slab_id)
    for pid in pile_ids:
        all_element_ids.Add(pid)
    new_group = doc.Create.NewGroup(all_element_ids)
    group_type = new_group.GroupType
    group_type.Name = group_name
    return new_group


def build_pile_symbol_map(doc, log_fn=None):
    all_pile_symbols = collect_pile_symbols(doc, log_fn)
    all_pile_symbols = sorted(all_pile_symbols, key=symbol_sort_key)
    symbol_map = {}
    pile_symbol_names = []
    for sym in all_pile_symbols:
        name = '{} : {}'.format(get_family_name(sym), get_type_name(sym))
        if name in symbol_map:
            name = '{} : {} [{}]'.format(
                get_family_name(sym), get_type_name(sym), get_id_value(sym.Id))
        symbol_map[name] = sym
        pile_symbol_names.append(name)
    return all_pile_symbols, symbol_map, pile_symbol_names


def compute_slab_layout(face_inf, slab_bottom_z):
    span_dir, span_length = find_longest_edge(face_inf)
    span_rotation_angle = math.atan2(span_dir.Y, span_dir.X)
    perp_dir = DB.XYZ(-span_dir.Y, span_dir.X, 0).Normalize()
    slab_z = slab_bottom_z
    vertices = get_face_vertices(face_inf)
    center_x = sum(v.X for v in vertices) / len(vertices)
    center_y = sum(v.Y for v in vertices) / len(vertices)
    slab_center = DB.XYZ(center_x, center_y, slab_z)
    u_coords = []
    v_coords = []
    for v in vertices:
        vec = v - slab_center
        u = vec.X * span_dir.X + vec.Y * span_dir.Y
        vv = vec.X * perp_dir.X + vec.Y * perp_dir.Y
        u_coords.append(u)
        v_coords.append(vv)
    slab_width = max(u_coords) - min(u_coords)
    slab_height = max(v_coords) - min(v_coords)
    return {
        'span_dir': span_dir,
        'span_length': span_length,
        'span_rotation_angle': span_rotation_angle,
        'perp_dir': perp_dir,
        'slab_z': slab_z,
        'slab_center': slab_center,
        'center_x': center_x,
        'center_y': center_y,
        'slab_width': slab_width,
        'slab_height': slab_height,
        'vertices': vertices,
    }
def find_next_core_number(doc):
    """Find the next available 'Core N' number."""
    all_groups = DB.FilteredElementCollector(doc).OfClass(DB.Group).ToElements()
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
