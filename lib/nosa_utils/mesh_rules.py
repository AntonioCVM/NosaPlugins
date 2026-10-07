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


BAR_SIZES_MM = (8, 10, 12, 16, 20, 25, 32, 40)
EDGE_UBAR_SHARE = 0.5      # SMDSC MS2 / MST1: edge U-bars carry half the area of the main bottom bars


def edge_ubar_dia_mm(u_dia, u_spacing, main_dia, main_spacing, share=EDGE_UBAR_SHARE):
    """The smallest bar from u_dia up whose U-bars at u_spacing give `share` of the main bottom area."""
    need = share * float(main_dia) ** 2 / float(main_spacing)
    for size in BAR_SIZES_MM:
        if size >= u_dia - 1e-6 and size ** 2 / float(u_spacing) >= need - 1e-9:
            return float(size)
    return float(BAR_SIZES_MM[-1])


HOLE_IGNORE_MM, HOLE_BOTTOM_MM, HOLE_TOP_MM = 150.0, 500.0, 1000.0   # SMDSC 6.2 holes in slabs
TRIMMER_ANCHOR_PHI = 45.0


def slab_hole_class(width_mm, length_mm):
    """
    SMDSC 6.2 for an isolated hole: 'ignore' (sides <= 150, bars run through), 'bottom' (<= 500: bars
    cut and trimmed with bars of equal area), 'both' (<= 1000: the top trimmed too, diagonals if
    h > 250) or 'design' (over 1000: the designer specifies it).
    """
    side = max(float(width_mm), float(length_mm))
    if side <= HOLE_IGNORE_MM + 1e-6:
        return u'ignore'
    if side <= HOLE_BOTTOM_MM + 1e-6:
        return u'bottom'
    if side <= HOLE_TOP_MM + 1e-6:
        return u'both'
    return u'design'


def trimmers_per_side(cut_extent_mm, spacing_mm):
    """Bars each side of a hole replacing the bars it cuts (equal area, half each side, at least one)."""
    cut = max(1, int(math.ceil(float(cut_extent_mm) / float(spacing_mm) - 1e-9)))
    return max(1, int(math.ceil(cut / 2.0)))


TORSION_SHARE = 0.75     # SMDSC Fig. 6.9 / EC2 9.3.1.3: each leg 3/4 of the mid-span steel
TORSION_REACH = 0.2      # ... over a fifth of the shorter span from the corner


def torsion_extra_spacing_mm(bottom_dia, bottom_spacing, top_dia=None, top_spacing=None, extra_dia=None):
    """
    Pitch of the extra top bars (extra_dia, default the bottom size) a held-down slab corner needs so
    the top gives 3/4 of the bottom area (the bottom mat already runs through the corner); None
    when the top mat already does. 25 mm steps down, never under 100.
    """
    need = TORSION_SHARE * float(bottom_dia) ** 2 / float(bottom_spacing)
    have = float(top_dia) ** 2 / float(top_spacing) if top_dia and top_spacing else 0.0
    if have >= need - 1e-9:
        return None
    dia = float(extra_dia or bottom_dia)
    pitch = dia ** 2 / (need - have)
    return max(FOUNDATION_MIN_PITCH_MM, 25.0 * math.floor(pitch / 25.0 + 1e-9))


def slab_corners(polygon):
    """
    Convex right-angled corners of a plan polygon whose edges run along X and Y: [(x, y, dx, dy)],
    (dx, dy) pointing into the slab along each edge.
    """
    pts = list(polygon)
    if len(pts) > 1 and abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        pts = pts[:-1]
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    out = []
    for i in range(n):
        a, v, b = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = (v[0] - a[0], v[1] - a[1])
        e2 = (b[0] - v[0], b[1] - v[1])
        if (e1[0] * e2[1] - e1[1] * e2[0]) * area <= 0.0:
            continue                                   # re-entrant (or straight) vertex
        along_x = [p for p in (a, b) if abs(p[1] - v[1]) < 1.0 and abs(p[0] - v[0]) > 1.0]
        along_y = [p for p in (a, b) if abs(p[0] - v[0]) < 1.0 and abs(p[1] - v[1]) > 1.0]
        if len(along_x) != 1 or len(along_y) != 1:
            continue
        out.append((v[0], v[1], 1.0 if along_x[0][0] > v[0] else -1.0, 1.0 if along_y[0][1] > v[1] else -1.0))
    return out


BAND_FACTOR = 1.5          # SMDSC 6.7: a band under the column when l > 1.5 (c + 3d)
BAND_SHARE = 2.0 / 3.0


def footing_band_mm(l_mm, c_mm, d_mm):
    """Width c + 3d of the band under the column for the bars spaced along l (SMDSC 6.7), else None."""
    band = float(c_mm) + 3.0 * float(d_mm)
    return band if float(l_mm) > BAND_FACTOR * band + 1e-6 else None


def band_layout_mm(lo_mm, hi_mm, count, band_lo_mm, band_hi_mm, max_pitch_mm=300.0,
                   min_pitch_mm=FOUNDATION_MIN_PITCH_MM):
    """
    Positions of `count` bars from lo to hi with at least two thirds of them in band_lo..band_hi (bars
    on both band edges) and the rest evenly in the outer strips, never wider than max_pitch apart;
    returns (band, left, right) position lists, or None if the band would be closer than min_pitch.
    """
    band_lo, band_hi = max(float(lo_mm), float(band_lo_mm)), min(float(hi_mm), float(band_hi_mm))
    wl, wr, wb = band_lo - lo_mm, hi_mm - band_hi, band_hi - band_lo
    if wb <= 0.0:
        return None
    n_out = count - int(math.ceil(BAND_SHARE * count - 1e-9))
    if abs(wl - wr) < 1.0:
        nl = nr = n_out // 2
    else:
        nl = int(math.floor(n_out * wl / (wl + wr) + 0.5))
        nr = n_out - nl
    nl = 0 if wl < 1.0 else max(nl, int(math.ceil(wl / max_pitch_mm - 1e-9)))
    nr = 0 if wr < 1.0 else max(nr, int(math.ceil(wr / max_pitch_mm - 1e-9)))
    nb = max(count - nl - nr, 2 * (nl + nr), 2)
    if wb / (nb - 1) < min_pitch_mm - 1e-6:
        return None
    band = [band_lo + wb * k / (nb - 1) for k in range(nb)]
    left = [band_lo - wl * k / nl for k in range(nl, 0, -1)] if nl else []
    right = [band_hi + wr * k / nr for k in range(1, nr + 1)] if nr else []
    return band, left, right


def _unique(notes):
    out = []
    for n in notes:
        if n not in out:
            out.append(n)
    return out


def stair_review(throat_mm, cover_mm, main_dia, main_spacing, dist_dia, dist_spacing, fck_mpa,
                 top_dia=None, top_spacing=None, label=u'Stair'):
    """
    SMDSC 6.8 (slab rules of 6.2 on the waist): main bars <= min(3h, 400) and As,min, distribution
    bars <= min(3.5h, 450) and >= 20 % of the main steel, top bars as main bars.
    Returns (main spacing, distribution spacing, top spacing, notes).
    """
    h, cover = float(throat_mm), float(cover_mm)
    main_dia, main_spacing = float(main_dia), float(main_spacing)
    dist_dia, dist_spacing = float(dist_dia), float(dist_spacing)
    notes = []
    main_spacing = _clamp(main_spacing, slab_max_pitch_mm(h), label, u'main bars', u'min(3h, 400)', notes)
    dist_spacing = _clamp(dist_spacing, min(3.5 * h, 450.0), label, u'distribution bars',
                          u'min(3.5h, 450)', notes)
    _min_steel(h, cover, [(u'main', main_dia, main_spacing, 0.0)], fck_mpa, label, notes)
    if area_per_m(dist_dia, dist_spacing) < 0.2 * area_per_m(main_dia, main_spacing) - 1e-6:
        notes.append(u'{}: distribution bars under 20 % of the main steel (SMDSC 6.2).'.format(label))
    if top_dia and top_spacing:
        top_spacing = _clamp(float(top_spacing), slab_max_pitch_mm(h), label, u'top bars', u'min(3h, 400)', notes)
    if main_dia < SLAB_MIN_DIA_MM:
        notes.append(u'{}: H{:.0f} main bars under the preferred H10 (SMDSC 6.2).'.format(label, main_dia))
    return main_spacing, dist_spacing, top_spacing, _unique(notes)
