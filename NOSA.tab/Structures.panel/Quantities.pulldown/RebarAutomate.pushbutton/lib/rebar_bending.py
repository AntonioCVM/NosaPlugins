# -*- coding: utf-8 -*-
"""Bending geometry of one bar: outer leg lengths, signed bend angles and mandrel (BS 8666 / BVBS)."""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

_PARALLEL_TOL = 1e-6
_FT_TO_MM = 304.8


def line_segment(length_mm, direction):
    return {'kind': 'line', 'length_mm': float(length_mm), 'dir': tuple(direction)}


def arc_segment(radius_mm, angle_deg):
    return {'kind': 'arc', 'radius_mm': float(radius_mm), 'angle_deg': float(angle_deg)}


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    return math.sqrt(_dot(a, a))


def bending_from_curves(curves, bar_dia_mm):
    """bending_legs for Revit centreline curves (Line / Arc, internal feet), or None."""
    from Autodesk.Revit.DB import Arc, Line
    segments = []
    for c in curves:
        if isinstance(c, Line):
            d = c.Direction
            segments.append(line_segment(c.Length * _FT_TO_MM, (d.X, d.Y, d.Z)))
        elif isinstance(c, Arc):
            segments.append(arc_segment(c.Radius * _FT_TO_MM, math.degrees(c.Length / c.Radius)))
        else:
            return None
    return bending_legs(segments, bar_dia_mm)


def bar_variants(rebar, bar_dia_mm):
    """(bending geometry or None, cut length mm) for every bar of a Revit Rebar element."""
    from Autodesk.Revit.DB.Structure import MultiplanarOption
    try:
        indices = range(rebar.NumberOfBarPositions)
    except Exception:
        indices = [0]
    bars = []
    for i in indices:
        try:
            if not rebar.DoesBarExistAtPosition(i):
                continue
        except Exception:
            pass
        try:
            curves = list(rebar.GetCenterlineCurves(False, False, False,
                                                    MultiplanarOption.IncludeOnlyPlanarCurves, i))
            bars.append((bending_from_curves(curves, bar_dia_mm),
                         round(sum(c.Length for c in curves) * _FT_TO_MM, 1)))
        except Exception:
            continue
    return bars


def variant_key(geometry, length_mm):
    """Bars with the same key are the same bar for the schedule (legs to 1 mm, else length)."""
    if geometry:
        return tuple((int(round(l)), round(a, 1)) for l, a in geometry['legs'])
    return ('length', int(round(length_mm)))


def bending_legs(segments, bar_dia_mm):
    """
    From a bar's centreline (alternating straight lines and bend arcs, in order)
    return {'legs': [(outer_length_mm, signed_bend_deg), ...], 'mandrel_mm': float or None},
    the last leg carrying a 0° bend; None when the bar is not a planar line/bend chain
    (e.g. a lapped circular link), which BVBS then exports without geometry.
    """
    lines = [s for s in segments if s['kind'] == 'line']
    if not lines:
        return None
    # Straight legs and the bend (arc) between each consecutive pair.
    bends = []
    previous = None
    for seg in segments:
        if seg['kind'] == 'arc':
            if previous != 'line':
                return None
            bends.append(seg)
            previous = 'arc'
        else:
            if previous == 'line':
                bends.append(None)
            previous = 'line'
    if previous == 'arc' or len(bends) != len(lines) - 1:
        return None

    normal = None
    for a, b in zip(lines, lines[1:]):
        c = _cross(a['dir'], b['dir'])
        if _norm(c) > _PARALLEL_TOL:
            normal = tuple(v / _norm(c) for v in c)
            break
    if normal is not None:
        for a, b in zip(lines, lines[1:]):
            c = _cross(a['dir'], b['dir'])
            if _norm(c) > _PARALLEL_TOL and abs(abs(_dot(c, normal)) - _norm(c)) > 1e-3:
                return None   # not planar: a BF3D bar

    half_dia = bar_dia_mm / 2.0
    extensions = [0.0] * len(lines)
    angles = []
    mandrel = None
    for i, bend in enumerate(bends):
        a, b = lines[i]['dir'], lines[i + 1]['dir']
        cos_t = max(-1.0, min(1.0, _dot(a, b) / (_norm(a) * _norm(b))))
        theta = math.degrees(math.acos(cos_t))
        c = _cross(a, b)
        sign = 1.0 if normal is None or _dot(c, normal) >= 0 else -1.0
        angles.append(sign * theta)
        if bend is None or theta < 1e-6:
            continue
        rc = bend['radius_mm']
        if mandrel is None:
            mandrel = 2.0 * rc - bar_dia_mm
        # Outer dimension: the leg runs to the intersection of the outer faces
        # (BS 8666 / BVBS measure legs to the outside of the bend, up to 90°).
        ext = (rc + half_dia) * math.tan(math.radians(min(theta, 90.0)) / 2.0)
        extensions[i] += ext
        extensions[i + 1] += ext

    legs = []
    for i, line in enumerate(lines):
        legs.append((line['length_mm'] + extensions[i], angles[i] if i < len(angles) else 0.0))
    return {'legs': legs, 'mandrel_mm': mandrel}
