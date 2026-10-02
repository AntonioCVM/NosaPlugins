# -*- coding: utf-8 -*-
"""
nosa_utils.solids
=================
Safe solid-geometry operations for Revit 2024-2027.

Boolean operations on real-world geometry (tangent faces, joined elements,
imported CAD) raise exceptions constantly. Every helper here guarantees a
usable return value instead of propagating the failure:

    get_solids(el)              -> list of positive-volume Solids
    get_element_solid(el)       -> best single solid (union, else largest)
    largest_solid(el)           -> largest solid by volume
    total_volume(el)            -> geometric volume sum (ft3)
    intersection_volume(a, b)   -> ft3, 0.0 on any failure
    solids_intersect(a, b)      -> bool
    safe_difference(a, cutter)  -> a minus cutter; falls back to a, never None
    union_solids(solids)        -> union, skipping members that fail
"""
from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.solids'


def _geo_options(view=None, compute_refs=False):
    opts = DB.Options()
    opts.ComputeReferences = compute_refs
    opts.IncludeNonVisibleObjects = False
    if view is not None:
        opts.View = view
    return opts


def iter_solids(element, view=None):
    """Yield every Solid with positive volume, including inside GeometryInstances."""
    try:
        geom = element.get_Geometry(_geo_options(view))
    except Exception:
        return
    if geom is None:
        return
    for obj in geom:
        try:
            if isinstance(obj, DB.Solid):
                if obj.Volume > 1e-9:
                    yield obj
            elif isinstance(obj, DB.GeometryInstance):
                for sub in obj.GetInstanceGeometry():
                    if isinstance(sub, DB.Solid) and sub.Volume > 1e-9:
                        yield sub
        except Exception:
            log_swallowed(_LOG, u'iter_solids')


def get_solids(element, view=None):
    return list(iter_solids(element, view))


def _largest(solids):
    best, best_vol = None, 0.0
    for s in solids:
        try:
            v = s.Volume
        except Exception:
            continue
        if v > best_vol:
            best, best_vol = s, v
    return best


def largest_solid(element, view=None):
    """Largest solid of the element by volume, or None."""
    return _largest(get_solids(element, view))


def union_solids(solids):
    """
    Union a list of solids into one. Members whose union step fails are
    skipped (partial union is returned rather than nothing).
    Returns None only if the list is empty.
    """
    result = None
    for s in solids:
        if result is None:
            result = s
            continue
        try:
            merged = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
                result, s, DB.BooleanOperationsType.Union)
            if merged is not None and merged.Volume > 0.0:
                result = merged
        except Exception:
            log_swallowed(_LOG, u'union_solids')
    return result


def get_element_solid(element, view=None):
    """
    Best single-solid representation of an element:
    one solid -> that solid; several -> union; union fails -> largest.
    """
    solids = get_solids(element, view)
    if not solids:
        return None
    if len(solids) == 1:
        return solids[0]
    merged = union_solids(solids)
    if merged is not None:
        return merged
    return _largest(solids)


def total_volume(element, view=None):
    """Geometric volume sum in ft3 — independent of Revit volume parameters."""
    total = 0.0
    for s in iter_solids(element, view):
        try:
            total += s.Volume
        except Exception:
            log_swallowed(_LOG, u'total_volume')
    return total


def intersection_volume(a, b):
    """Intersection volume in ft3; 0.0 if disjoint, invalid or the boolean fails."""
    if a is None or b is None:
        return 0.0
    try:
        inter = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            a, b, DB.BooleanOperationsType.Intersect)
        if inter is None:
            return 0.0
        v = inter.Volume
        return v if v > 0.0 else 0.0
    except Exception:
        return 0.0


def solids_intersect(a, b, min_volume_ft3=1e-3):
    return intersection_volume(a, b) > min_volume_ft3


def safe_difference(solid, cutter):
    """
    solid minus cutter, never None: on any failure (no intersection, boolean
    exception, empty result) the original solid is returned unchanged.
    """
    if solid is None:
        return None
    if cutter is None:
        return solid
    if intersection_volume(solid, cutter) <= 0.0:
        return solid
    try:
        cut = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
            solid, cutter, DB.BooleanOperationsType.Difference)
    except Exception:
        return solid
    if cut is None:
        return solid
    try:
        if cut.Volume <= 0.0:
            return solid
    except Exception:
        log_swallowed(_LOG, u'safe_difference')
    return cut
