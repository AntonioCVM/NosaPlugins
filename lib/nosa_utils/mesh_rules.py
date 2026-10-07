# -*- coding: utf-8 -*-
"""
nosa_utils.mesh_rules — bar meshes of slabs (IStructE SMDSC 6.2) and foundations (SMDSC 6.7),
EC2 9.3 / 9.8 with the UK NA. Pure Python.

Every mat direction is checked against the minimum tension steel 0.26 fctm/fyk bt d >= 0.0013 bt d
and the pitch limits; a pitch over the maximum is brought down to it (25 mm steps), the rest is
reported. The plugin lays both directions at one pitch, so the stricter (main-bar) limit holds.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

FYK_MPA = 500.0
SLAB_MIN_DIA_MM = 10.0
FOUNDATION_MIN_DIA_MM = 16.0
FOUNDATION_COVER_MM, PILED_BOTTOM_COVER_MM = 75.0, 100.0
FOUNDATION_MIN_PITCH_MM = 100.0


def fctm_mpa(fck):
    return 0.30 * fck ** (2.0 / 3.0) if fck <= 50 else 2.12 * math.log(1.0 + (fck + 8.0) / 10.0)


def min_ratio(fck_mpa, fyk_mpa=FYK_MPA):
    """As,min / (bt d): max(0.26 fctm/fyk, 0.0013) (0.0015 for C30/37)."""
    return max(0.26 * fctm_mpa(fck_mpa) / fyk_mpa, 0.0013)


def area_per_m(dia_mm, spacing_mm):
    return math.pi * dia_mm ** 2 / 4.0 * 1000.0 / spacing_mm


def slab_max_pitch_mm(h_mm):
    """Main bars min(3h, 400) (secondary min(3.5h, 450): the main limit governs one common pitch)."""
    return min(3.0 * h_mm, 400.0)


def foundation_max_pitch_mm(ratio):
    """SMDSC 6.7: 300 up to 0.5 % of steel, 225 up to 1 %, 175 beyond."""
    if ratio <= 0.005 + 1e-9:
        return 300.0
    if ratio < 0.01 - 1e-9:
        return 225.0
    return 175.0


def _clamp(spacing, most, label, name, rule, notes):
    if spacing > most + 1e-6:
        used = 25.0 * math.floor(most / 25.0)
        notes.append(u'{}: {} at {:.0f} over {} = {:.0f}: {:.0f} mm used.'.format(
            label, name, spacing, rule, most, used))
        return used
    return spacing


def _min_steel(h_mm, cover_mm, layers, fck, label, notes):
    need_ratio = min_ratio(fck)
    for name, dia, spacing, depth_in in layers:
        d = h_mm - cover_mm - depth_in - dia / 2.0
        need = need_ratio * 1000.0 * d
        have = area_per_m(dia, spacing)
        if have < need - 1e-6:
            notes.append(u'{}: {} H{:.0f} at {:.0f} give {:.0f} mm2/m, under As,min {:.0f} '
                         u'({:.2f} % of b d, EC2 9.2.1.1).'.format(label, name, dia, spacing, have, need,
                                                                 100 * need_ratio))


def slab_review(h_mm, cover_mm, dia_x, dia_y, spacing, fck_mpa, top=None, label=u'Slab'):
    """
    SMDSC 6.2 review of a slab mesh. top: (top dia x, top dia y, top spacing, top cover) or None.
    Returns (spacing, top spacing, notes).
    """
    h, cover = float(h_mm), float(cover_mm)
    dia_x, dia_y, spacing = float(dia_x), float(dia_y), float(spacing)
    notes = []
    most = slab_max_pitch_mm(h)
    spacing = _clamp(spacing, most, label, u'bottom bars', u'min(3h, 400)', notes)
    _min_steel(h, cover, [(u'bottom X', dia_x, spacing, 0.0), (u'bottom Y', dia_y, spacing, dia_x)],
               fck_mpa, label, notes)
    top_spacing = None
    if top:
        tx, ty, ts, tc = [float(v) for v in top]
        top_spacing = _clamp(ts, most, label, u'top bars', u'min(3h, 400)', notes)
        for dia in (tx, ty):
            if dia < SLAB_MIN_DIA_MM:
                notes.append(u'{}: H{:.0f} under the preferred H10 (SMDSC 6.2).'.format(label, dia))
    for dia in (dia_x, dia_y):
        if dia < SLAB_MIN_DIA_MM:
            notes.append(u'{}: H{:.0f} under the preferred H10 (SMDSC 6.2).'.format(label, dia))
    return spacing, top_spacing, _unique(notes)


def foundation_review(h_mm, cover_mm, dia_x, dia_y, spacing, fck_mpa, top=None, piled=False,
                      label=u'Foundation'):
    """SMDSC 6.7 review of a footing / pile cap / raft mesh. Returns (spacing, top spacing, notes)."""
    h, cover = float(h_mm), float(cover_mm)
    dia_x, dia_y, spacing = float(dia_x), float(dia_y), float(spacing)
    notes = []
    ratio = area_per_m(max(dia_x, dia_y), spacing) / (1000.0 * max(h - cover, 1.0))
    spacing = _clamp(spacing, foundation_max_pitch_mm(ratio), label, u'bottom bars',
                     u'the SMDSC 6.7 maximum for {:.2f} % of steel'.format(100 * ratio), notes)
    if spacing < FOUNDATION_MIN_PITCH_MM - 1e-6:
        notes.append(u'{}: bars at {:.0f} under the 100 mm minimum (SMDSC 6.7).'.format(label, spacing))
    _min_steel(h, cover, [(u'bottom X', dia_x, spacing, 0.0), (u'bottom Y', dia_y, spacing, dia_x)],
               fck_mpa, label, notes)
    need_cover = PILED_BOTTOM_COVER_MM if piled else FOUNDATION_COVER_MM
    if cover < need_cover - 1e-6:
        notes.append(u'{}: bottom cover {:.0f} under the {:.0f} mm SMDSC 6.7 gives {}.'.format(
            label, cover, need_cover, u'a pile cap' if piled else u'foundations'))
    dias = [dia_x, dia_y]
    top_spacing = None
    if top:
        tx, ty, ts, tc = [float(v) for v in top]
        top_spacing = _clamp(ts, foundation_max_pitch_mm(ratio), label, u'top bars',
                             u'the SMDSC 6.7 maximum', notes)
        dias += [tx, ty]
    for dia in dias:
        if dia < FOUNDATION_MIN_DIA_MM:
            notes.append(u'{}: H{:.0f} under H16, the smallest SMDSC 6.7 allows (lacers apart).'.format(label, dia))
    return spacing, top_spacing, _unique(notes)


def _unique(notes):
    out = []
    for n in notes:
        if n not in out:
            out.append(n)
    return out
