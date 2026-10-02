# -*- coding: utf-8 -*-
"""
Geometry Utilities
Common geometry functions used across multiple scripts.
"""

from Autodesk.Revit.DB import XYZ, LocationPoint, LocationCurve, Options, Solid
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.geometry'

# =============================================================================
# ELEMENT CENTER EXTRACTION
# =============================================================================

def get_element_center(element, use_bbox_fallback=True):
    """
    Get the center point of an element.
    Tries multiple methods: LocationPoint, LocationCurve, BoundingBox.
    
    Args:
        element: Revit element
        use_bbox_fallback (bool): If True, use bounding box as fallback
        
    Returns:
        XYZ: Center point, or None if cannot be determined
        
    Example:
        >>> center = get_element_center(wall)
        >>> if center:
        >>>     print("Center at: {}, {}, {}".format(center.X, center.Y, center.Z))
    """
    try:
        # Method 1: LocationPoint
        location = getattr(element, 'Location', None)
        if location:
            if isinstance(location, LocationPoint) and location.Point:
                return location.Point
            
            # Method 2: LocationCurve midpoint
            if isinstance(location, LocationCurve) and location.Curve:
                curve = location.Curve
                try:
                    return curve.Evaluate(0.5, True)
                except Exception:
                    # Fallback for curves without Evaluate
                    start = curve.GetEndPoint(0)
                    end = curve.GetEndPoint(1)
                    return XYZ(
                        (start.X + end.X) / 2.0,
                        (start.Y + end.Y) / 2.0,
                        (start.Z + end.Z) / 2.0
                    )
        
        # Method 3: BoundingBox center
        if use_bbox_fallback:
            return get_bounding_box_center(element)
        
    except Exception:
        log_swallowed(_LOG, u'get_element_center')
    
    return None


def get_bounding_box_center(element, view=None):
    """
    Get center point from element's bounding box.
    
    Args:
        element: Revit element
        view: Optional view for bounding box calculation
        
    Returns:
        XYZ: Center point, or None if no bounding box
    """
    try:
        bbox = element.get_BoundingBox(view)
        if bbox and bbox.Min and bbox.Max:
            return XYZ(
                (bbox.Min.X + bbox.Max.X) / 2.0,
                (bbox.Min.Y + bbox.Max.Y) / 2.0,
                (bbox.Min.Z + bbox.Max.Z) / 2.0
            )
    except Exception:
        log_swallowed(_LOG, u'get_bounding_box_center')
    
    return None


# =============================================================================
# SOLID GEOMETRY EXTRACTION
# =============================================================================

def get_solid_from_element(element, options=None):
    """
    Extract solid geometry from element.
    Returns the first solid with volume > 0.
    
    Args:
        element: Revit element
        options (Options): Geometry options (if None, creates default)
        
    Returns:
        Solid: First solid found, or None
        
    Example:
        >>> solid = get_solid_from_element(wall)
        >>> if solid:
        >>>     print("Volume:", solid.Volume)
    """
    if options is None:
        options = Options()
        options.ComputeReferences = True
        options.IncludeNonVisibleObjects = False
    
    try:
        geometry = element.get_Geometry(options)
        if not geometry:
            return None
        
        for geo_obj in geometry:
            # Direct solid
            if isinstance(geo_obj, Solid) and geo_obj.Volume > 0:
                return geo_obj
            
            # Solid inside GeometryInstance
            if hasattr(geo_obj, 'GetInstanceGeometry'):
                try:
                    instance_geo = geo_obj.GetInstanceGeometry()
                    for sub_obj in instance_geo:
                        if isinstance(sub_obj, Solid) and sub_obj.Volume > 0:
                            return sub_obj
                except Exception:
                    continue
    except Exception:
        log_swallowed(_LOG, u'get_solid_from_element')
    
    return None


# =============================================================================
# GEOMETRIC CALCULATIONS
# =============================================================================

def bboxes_overlap(bbox1, bbox2, tolerance_ft=0.0):
    """
    Check if two Revit BoundingBoxXYZ overlap in all three axes, with an
    optional tolerance margin (in feet) applied on each side — 0.0 gives a
    strict overlap test (ClashReport's use case), a positive value gives a
    proximity test (ElementJoin's "within N mm" use case).

    Args:
        bbox1, bbox2 (BoundingBoxXYZ): the two boxes to compare
        tolerance_ft (float): margin added to each box's extents (feet)

    Returns:
        bool: True if the (possibly expanded) boxes overlap on every axis
    """
    if not bbox1 or not bbox2:
        return False

    def _overlaps_1d(a_min, a_max, b_min, b_max, tol):
        return a_min - tol <= b_max and b_min - tol <= a_max

    return (
        _overlaps_1d(bbox1.Min.X, bbox1.Max.X, bbox2.Min.X, bbox2.Max.X, tolerance_ft) and
        _overlaps_1d(bbox1.Min.Y, bbox1.Max.Y, bbox2.Min.Y, bbox2.Max.Y, tolerance_ft) and
        _overlaps_1d(bbox1.Min.Z, bbox1.Max.Z, bbox2.Min.Z, bbox2.Max.Z, tolerance_ft)
    )


def calculate_distance_2d(point1, point2):
    """
    Calculate 2D distance (XY plane only) between two points.
    
    Args:
        point1 (XYZ): First point
        point2 (XYZ): Second point
        
    Returns:
        float: Distance in Revit internal units
    """
    import math
    return math.sqrt(
        (point1.X - point2.X) ** 2 +
        (point1.Y - point2.Y) ** 2
    )


def calculate_distance_3d(point1, point2):
    """
    Calculate 3D distance between two points.
    
    Args:
        point1 (XYZ): First point
        point2 (XYZ): Second point
        
    Returns:
        float: Distance in Revit internal units
    """
    import math
    return math.sqrt(
        (point1.X - point2.X) ** 2 +
        (point1.Y - point2.Y) ** 2 +
        (point1.Z - point2.Z) ** 2
    )


def point_in_polygon(point_x, point_y, polygon):
    """
    Check if a 2D point is inside a polygon using ray casting algorithm.
    
    Args:
        point_x (float): X coordinate of point
        point_y (float): Y coordinate of point
        polygon (list): List of (x, y) tuples representing polygon vertices
        
    Returns:
        bool: True if point is inside polygon
        
    Example:
        >>> polygon = [(0, 0), (10, 0), (10, 10), (0, 10)]
        >>> point_in_polygon(5, 5, polygon)  # Returns True
        >>> point_in_polygon(15, 5, polygon)  # Returns False
    """
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if ((p1y > point_y) != (p2y > point_y)) and \
           (point_x < (p2x - p1x) * (point_y - p1y) / (p2y - p1y + 1e-12) + p1x):
            inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside


def calculate_polygon_area(polygon):
    """Calculate the area of a polygon using shoelace formula."""
    area = 0.0
    n = len(polygon)
    if n < 3:
        return 0.0
    
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i][0] * polygon[j][1]
        area -= polygon[j][0] * polygon[i][1]
    
    return abs(area) / 2.0


def point_in_polygons(point_x, point_y, polygons):
    """
    Check if point is inside the main polygon and outside all holes.
    Automatically identifies the largest polygon as the outer boundary.
    
    Args:
        point_x (float): X coordinate
        point_y (float): Y coordinate
        polygons (list): List of polygons - first is outer, rest are holes
        
    Returns:
        bool: True if inside main polygon and outside all holes
    """
    if not polygons or len(polygons) == 0:
        return False
    
    # Sort polygons by area (largest is outer)
    # Only sort if we have more than 1 polygon, to ensure the assumption holds
    if len(polygons) > 1:
        # Create list of (area, polygon) tuples
        poly_areas = []
        for poly in polygons:
            area = calculate_polygon_area(poly)
            poly_areas.append((area, poly))
        
        # Sort descending by area
        poly_areas.sort(key=lambda x: x[0], reverse=True)
        sorted_polygons = [p[1] for p in poly_areas]
    else:
        sorted_polygons = polygons
    
    # Check if inside outer polygon (largest)
    if not point_in_polygon(point_x, point_y, sorted_polygons[0]):
        return False
    
    # Check if inside any hole
    for hole in sorted_polygons[1:]:
        if point_in_polygon(point_x, point_y, hole):
            try:
                # Only consider it a hole if the point is strictly inside
                # If area is tiny, it might be artifact, but generally if in hole -> False
                return False
            except Exception:
                log_swallowed(_LOG, u'point_in_polygons')
    
    return True
