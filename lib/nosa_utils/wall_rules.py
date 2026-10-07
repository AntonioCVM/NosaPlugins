# -*- coding: utf-8 -*-
"""
nosa_utils.wall_rules — walls to IStructE SMDSC 6.5 / Model Detail MW1 (EC2 9.6 + UK NA). Pure Python.

Horizontal bars go outside the verticals (cover is measured to them). Minimum and maximum areas,
bar sizes, pitches and the links of heavily reinforced walls are checked; MW1 gives the nominal
reinforcement by thickness when the designer gives none.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

MIN_THICKNESS_MM = 150.0
MAX_PITCH_MM = 400.0
MIN_VERTICAL_DIA_MM = 12.0
KICKER_MM, KICKER_BELOW_GROUND_MM = 75.0, 150.0

# MW1: (thickness up to, vertical dia, vertical pitch, horizontal dia, horizontal pitch), per face
MW1 = ((175.0, 12, 300, 10, 200), (200.0, 12, 250, 10, 200), (250.0, 12, 200, 10, 200),
       (300.0, 16, 300, 10, 200), (400.0, 16, 250, 12, 200), (500.0, 16, 200, 12, 150),
       (600.0, 20, 250, 16, 200), (700.0, 20, 200, 16, 200), (800.0, 20, 200, 16, 200))


def mw1_nominal(thickness_mm):
    """{'vert_dia', 'vert_spacing', 'horiz_dia', 'horiz_spacing'} of Model Detail MW1, or None outside 150-800."""
    if thickness_mm < MIN_THICKNESS_MM:
        return None
    for top, vd, vp, hd, hp in MW1:
        if thickness_mm <= top + 1e-6:
            return {'vert_dia': vd, 'vert_spacing': vp, 'horiz_dia': hd, 'horiz_spacing': hp}
    return None


def max_pitch_mm(thickness_mm):
    """Vertical and horizontal bars: min(3 t, 400)."""
    return min(3.0 * thickness_mm, MAX_PITCH_MM)


def area_per_m(dia_mm, spacing_mm):
    return math.pi * dia_mm ** 2 / 4.0 * 1000.0 / spacing_mm


def review(thickness_mm, vert_dia_mm, vert_spacing_mm, horiz_dia_mm, horiz_spacing_mm, both_faces=True,
           ties=False, tie_spacing_mm=None, label=u'Wall'):
    """
    SMDSC 6.5 review of a wall. Returns (vertical pitch, horizontal pitch, notes): pitches over
    min(3 t, 400) are brought down to it (25 mm steps) and said so; the rest is reported.
    """
    t = float(thickness_mm)
    vd, vs, hd, hs = float(vert_dia_mm), float(vert_spacing_mm), float(horiz_dia_mm), float(horiz_spacing_mm)
    notes = []
    if t < MIN_THICKNESS_MM:
        notes.append(u'{}: {:.0f} mm thick, under the 150 mm SMDSC 6.5 recommends.'.format(label, t))
    most = max_pitch_mm(t)
    out = []
    for name, spacing in ((u'vertical', vs), (u'horizontal', hs)):
        used = spacing
        if spacing > most + 1e-6:
            used = 25.0 * math.floor(most / 25.0)
            notes.append(u'{}: {} bars at {:.0f} over min(3t, 400) = {:.0f}: {:.0f} mm used (SMDSC 6.5).'.format(
                label, name, spacing, most, used))
        out.append(used)
    vs, hs = out
    faces = 2.0 if both_faces else 1.0
    ac_per_m = t * 1000.0
    as_v = faces * area_per_m(vd, vs)
    as_h = area_per_m(hd, hs)                              # one face
    if as_v < 0.002 * ac_per_m - 1e-6:
        notes.append(u'{}: vertical steel {:.0f} mm2/m under 0.2 % of the wall ({:.0f}) (SMDSC 6.5).'.format(
            label, as_v, 0.002 * ac_per_m))
    if as_v > 0.04 * ac_per_m + 1e-6:
        notes.append(u'{}: vertical steel {:.1f} % over 4 % (SMDSC 6.5).'.format(label, 100 * as_v / ac_per_m))
    need_h = max(0.25 * as_v / faces, 0.001 * ac_per_m)
    if as_h < need_h - 1e-6:
        notes.append(u'{}: horizontal steel {:.0f} mm2/m a face under max(25 % of the verticals, 0.1 %) = '
                     u'{:.0f} (SMDSC 6.5).'.format(label, as_h, need_h))
    if vd < MIN_VERTICAL_DIA_MM:
        notes.append(u'{}: H{:.0f} verticals under H12, the minimum for a robust cage (SMDSC 6.5).'.format(label, vd))
    if hd < vd / 4.0 - 1e-6:
        notes.append(u'{}: H{:.0f} horizontals under a quarter of the verticals (SMDSC 6.5).'.format(label, hd))
    if as_v > 0.02 * ac_per_m + 1e-6:
        link_pitch = min(16.0 * vd, 2.0 * t)
        if not ties:
            notes.append(u'{}: vertical steel over 2 %: links are needed at <= {:.0f} mm up the wall and '
                         u'<= {:.0f} mm along it (SMDSC 6.5).'.format(label, link_pitch, 2.0 * t))
        elif tie_spacing_mm and float(tie_spacing_mm) > link_pitch + 1e-6:
            notes.append(u'{}: wall links at {:.0f} over min(16 phi, 2t) = {:.0f} (SMDSC 6.5).'.format(
                label, float(tie_spacing_mm), link_pitch))
    return vs, hs, notes
