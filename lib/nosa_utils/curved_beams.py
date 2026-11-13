# -*- coding: utf-8 -*-
"""
nosa_utils.curved_beams — plan rules of beams curved on plan (T8.58), in plain numbers: angle range of the
beam's own solid, radii of the bars across the width, radial link positions with the pitch kept at the outer
leg. Angles in radians (counter-clockwise from +X, like Revit); lengths in mm.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math


def wrap(angle):
    """angle in [-pi, pi)."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def angle_range(points, center, a_start, sweep):
    """
    (t_min, t_max, r_min, r_max) of plan points (x, y) about center: t is the angle walked from a_start in the
    sweep's sense (sweep signed, + is CCW), so a beam end cut back by a column gives t_min > 0.
    """
    sign = 1.0 if sweep >= 0 else -1.0
    a_mid = a_start + sweep / 2.0
    ts, rs = [], []
    for x, y in points:
        dx, dy = x - center[0], y - center[1]
        ts.append(sign * wrap(math.atan2(dy, dx) - a_mid) + abs(sweep) / 2.0)
        rs.append(math.hypot(dx, dy))
    return min(ts), max(ts), min(rs), max(rs)


def angle_at(a_start, sweep, t):
    """Revit angle of the walked angle t."""
    return a_start + (1.0 if sweep >= 0 else -1.0) * t


def bar_radii(r_inner_mm, r_outer_mm, inset_mm, count):
    """Radii of count bars across the width, the outer two inset_mm inside the faces."""
    lo, hi = r_inner_mm + inset_mm, r_outer_mm - inset_mm
    if count <= 1 or hi <= lo:
        return [(lo + hi) / 2.0]
    return [lo + (hi - lo) * i / (count - 1.0) for i in range(count)]


def link_pitch_at_centre_mm(pitch_mm, r_centre_mm, r_outer_leg_mm):
    """Pitch along the centre of the links that keeps the outer legs at pitch_mm (the widest gap)."""
    if r_outer_leg_mm <= 0 or r_centre_mm <= 0:
        return pitch_mm
    return pitch_mm * r_centre_mm / r_outer_leg_mm


def link_angles(t_min, t_max, r_centre_mm, pitch_centre_mm, end_clear_mm):
    """Walked angles of links exactly pitch_centre_mm apart on the centre arc, centred between the end clearances."""
    length = r_centre_mm * (t_max - t_min)
    lo, hi = end_clear_mm, length - end_clear_mm
    span = hi - lo
    if span <= 0 or pitch_centre_mm <= 0:
        return []
    gaps = int(math.floor(span / pitch_centre_mm + 1e-9))
    if gaps == 0:
        return [t_min + (lo + span / 2.0) / r_centre_mm]
    start = lo + (span - gaps * pitch_centre_mm) / 2.0
    return [t_min + (start + k * pitch_centre_mm) / r_centre_mm for k in range(gaps + 1)]


def torsion_note(label=u'Beam'):
    """A beam curved on plan carries torsion: closed links and the side bars are a design check."""
    return (u'{}: curved on plan, so it carries torsion: links are closed and the bars run round the curve; '
            u'check torsion links and longitudinal bars against the design (EC2 6.3).'.format(label))
