# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Wall Rebar (Phase F7)
============================================================================

Category module for structural walls. Pure geometry — returns curve
sets for rebar_engine.RebarWrapper. Straight walls only in v1.
Openings / boundary ties / dowels are deferred.
"""
import os

from Autodesk.Revit import DB

_HERE = os.path.dirname(os.path.abspath(__file__))
re_engine = None

_MM_PER_FT = 304.8


def _ensure_engine():
    global re_engine
    if re_engine is None:
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


def get_wall_axis(host):
    """Straight wall centreline as DB.Line."""
    loc = getattr(host, 'Location', None)
    curve = getattr(loc, 'Curve', None) if loc is not None else None
    if curve is None:
        raise ValueError(u'Wall has no LocationCurve.')
    if not isinstance(curve, DB.Line):
        raise ValueError(u'Curved walls are not supported yet.')
    return curve


def _wall_height_ft(host):
    """Unconnected height or bbox Z extent."""
    try:
        p = host.get_Parameter(DB.BuiltInParameter.WALL_USER_HEIGHT_PARAM)
        if p and p.HasValue:
            h = p.AsDouble()
            if h > 1e-6:
                return h
    except Exception:
        pass
    bbox = host.get_BoundingBox(None)
    if bbox is None:
        raise ValueError(u'Could not determine wall height.')
    return abs(bbox.Max.Z - bbox.Min.Z)


def _wall_faces(cover_mgr, axis_dir):
    """
    Classify wall faces into (exterior-ish, interior-ish, top, bottom).

    Side faces: normal roughly perpendicular to axis (horizontal).
    Top/bottom: |normal.Z| > 0.7.
    """
    sides = []
    top = bottom = None
    for f in cover_mgr.faces:
        z = f.normal.Z
        if z > 0.7:
            if top is None or f.normal.Z > top.normal.Z:
                top = f
            continue
        if z < -0.7:
            if bottom is None or f.normal.Z < bottom.normal.Z:
                bottom = f
            continue
        if abs(f.normal.DotProduct(axis_dir)) < 0.35 and abs(z) < 0.35:
            sides.append(f)

    if len(sides) < 1:
        raise ValueError(u'Could not find wall side faces.')
    # Prefer the two largest side faces if more than two (openings etc.)
    sides = sorted(sides, key=lambda fi: getattr(fi, 'area', 0.0) or 0.0, reverse=True)
    face_a = sides[0]
    face_b = sides[1] if len(sides) > 1 else None
    return face_a, face_b, top, bottom


def _evenly_spaced_mm(length_mm, spacing_mm, end_clear_mm):
    """Positions from end_clear to length-end_clear at spacing (inclusive ends)."""
    if length_mm <= 2.0 * end_clear_mm or spacing_mm <= 0:
        return []
    usable = length_mm - 2.0 * end_clear_mm
    if usable < 1.0:
        return [length_mm / 2.0]
    n = int(usable / spacing_mm) + 1
    if n < 2:
        return [end_clear_mm + usable / 2.0]
    return [end_clear_mm + i * usable / float(n - 1) for i in range(n)]


def build_wall_reinforcement(doc, host, cover_mm,
                              vert_dia_mm, vert_spacing_mm,
                              horiz_dia_mm, horiz_spacing_mm,
                              both_faces=True, end_clear_mm=50.0):
    """
    Build vertical + horizontal mesh curve sets for one straight wall.

    Returns:
        {
          'vertical_sets': [ {curves, spacing_mm, array_length_mm, normal, label}, ... ],
          'horizontal_sets': [ ... ],
          'warnings': [unicode, ...],
        }
    """
    engine = _ensure_engine()
    axis = get_wall_axis(host)
    axis_dir = axis.Direction.Normalize()
    p0 = axis.GetEndPoint(0)
    length_mm = axis.Length * _MM_PER_FT
    height_ft = _wall_height_ft(host)
    height_mm = height_ft * _MM_PER_FT

    cover_mgr = engine.CoverGeometryManager(doc, host)
    face_a, face_b, top, bottom = _wall_faces(cover_mgr, axis_dir)

    faces = [face_a]
    if both_faces and face_b is not None:
        faces.append(face_b)

    warnings = []
    if both_faces and face_b is None:
        warnings.append(u'Only one side face found — mesh placed on a single face.')

    # Vertical extent of bars
    z0 = p0.Z
    try:
        bbox = host.get_BoundingBox(None)
        if bbox is not None:
            z0 = bbox.Min.Z
    except Exception:
        pass

    vert_bottom_z = z0 + (cover_mm + vert_dia_mm / 2.0) / _MM_PER_FT
    vert_top_z = z0 + height_ft - (cover_mm + vert_dia_mm / 2.0) / _MM_PER_FT
    if vert_top_z <= vert_bottom_z + 1.0 / _MM_PER_FT:
        raise ValueError(u'Wall is too short for the given cover and bar diameter.')

    vert_positions = _evenly_spaced_mm(length_mm, vert_spacing_mm, end_clear_mm)
    horiz_positions = _evenly_spaced_mm(height_mm, horiz_spacing_mm, end_clear_mm)

    vertical_sets = []
    horizontal_sets = []

    for face in faces:
        face_normal = face.normal.Normalize()
        # Point on the cover plane of this face
        cover_pt = engine.compute_cover_point(face, cover_mm + vert_dia_mm / 2.0)

        # Vertical bars: first bar at first station along axis, then Set
        if vert_positions:
            d0_mm = vert_positions[0]
            origin = p0 + axis_dir.Multiply(d0_mm / _MM_PER_FT)
            # Project onto face cover plane: keep XY from origin along axis,
            # replace depth with cover_pt's projection along face normal
            depth = (cover_pt - p0).DotProduct(face_normal)
            bar_xy = p0 + axis_dir.Multiply(d0_mm / _MM_PER_FT) + face_normal.Multiply(depth)
            # Keep Z from vertical range
            start = DB.XYZ(bar_xy.X, bar_xy.Y, vert_bottom_z)
            end = DB.XYZ(bar_xy.X, bar_xy.Y, vert_top_z)
            # Correct XY to sit on cover plane at this station
            start = p0 + axis_dir.Multiply(d0_mm / _MM_PER_FT) + face_normal.Multiply(depth)
            start = DB.XYZ(start.X, start.Y, vert_bottom_z)
            end = DB.XYZ(start.X, start.Y, vert_top_z)
            curves = [DB.Line.CreateBound(start, end)]
            array_mm = (vert_positions[-1] - vert_positions[0]) if len(vert_positions) > 1 else 0.0
            spacing = vert_spacing_mm
            if len(vert_positions) > 1:
                spacing = (vert_positions[-1] - vert_positions[0]) / float(len(vert_positions) - 1)
            vertical_sets.append({
                'curves': curves,
                'spacing_mm': spacing,
                'array_length_mm': array_mm,
                'normal': axis_dir,
                'count': len(vert_positions),
                'label': u'Wall Vertical Mesh',
            })

        # Horizontal bars: first bar at first height, propagate vertically
        if horiz_positions:
            h0_mm = horiz_positions[0]
            depth = (cover_pt - p0).DotProduct(face_normal)
            # Clearance from wall ends along length
            clear_ft = end_clear_mm / _MM_PER_FT
            start = p0 + axis_dir.Multiply(clear_ft) + face_normal.Multiply(depth)
            end = p0 + axis_dir.Multiply(axis.Length - clear_ft) + face_normal.Multiply(depth)
            z = z0 + h0_mm / _MM_PER_FT
            start = DB.XYZ(start.X, start.Y, z)
            end = DB.XYZ(end.X, end.Y, z)
            if start.DistanceTo(end) < 1.0 / _MM_PER_FT:
                continue
            curves = [DB.Line.CreateBound(start, end)]
            array_mm = (horiz_positions[-1] - horiz_positions[0]) if len(horiz_positions) > 1 else 0.0
            spacing = horiz_spacing_mm
            if len(horiz_positions) > 1:
                spacing = (horiz_positions[-1] - horiz_positions[0]) / float(len(horiz_positions) - 1)
            horizontal_sets.append({
                'curves': curves,
                'spacing_mm': spacing,
                'array_length_mm': array_mm,
                'normal': DB.XYZ.BasisZ,
                'count': len(horiz_positions),
                'label': u'Wall Horizontal Mesh',
            })

    if not vertical_sets and not horizontal_sets:
        raise ValueError(u'No wall reinforcement curves could be generated.')

    return {
        'vertical_sets': vertical_sets,
        'horizontal_sets': horizontal_sets,
        'warnings': warnings,
    }
