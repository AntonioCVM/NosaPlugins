# -*- coding: utf-8 -*-
"""
nosa_utils.links — links (stirrups, ties) to IStructE SMDSC 6.3 / EC2 9.2.2 + UK NA. Pure Python.

Shared by every element that has links: the minimum shear ratio and preferred link size hold for
any of them; the beam rules (pitch, legs across the width, side bars, open links) are below, and
the column rules of SMDSC 6.4 join them with T8.38.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

FYK_MPA = 500.0
MIN_LINK_DIA_MM = 8.0            # SMDSC 6.3: preferred minimum
MAX_PITCH_MM = 300.0
MAX_LATERAL_LEG_MM = 600.0
MAX_BAR_TO_LEG_MM = 150.0        # no bar further than this from a vertical leg
OPEN_LINK_WIDTH_MM = 450.0       # open links (with a locking link) from this rib width
SIDE_BARS_DEPTH_MM = 1000.0      # side bars H16 at <= 250 from this depth
SIDE_BAR_DIA_MM = 16.0
SIDE_BAR_PITCH_MM = 250.0


def rho_w_min(fck_mpa, fyk_mpa=FYK_MPA):
    """EC2 9.2.2(5) with the UK NA: 0.08 sqrt(fck) / fyk (0.085 % for C30/37 in SMDSC 6.3)."""
    return 0.08 * math.sqrt(fck_mpa) / fyk_mpa


def link_ratio(legs, link_dia_mm, spacing_mm, width_mm):
    """Asw / (s bw) of links with `legs` vertical legs."""
    return legs * math.pi * link_dia_mm ** 2 / 4.0 / (spacing_mm * width_mm)


def effective_depth_mm(height_mm, cover_mm, link_dia_mm, bar_dia_mm):
    return height_mm - cover_mm - link_dia_mm - bar_dia_mm / 2.0


def pitch_limits_mm(d_mm, legs=2, compression_bar_dia_mm=None):
    """(minimum, maximum) link pitch: max(100, 50 + 12.5 legs) and min(300, 0.75 d, 12 phi')."""
    least = max(100.0, 50.0 + 12.5 * legs)
    most = min(MAX_PITCH_MM, 0.75 * d_mm)
    if compression_bar_dia_mm:
        most = min(most, 12.0 * compression_bar_dia_mm)
    return least, most


def legs_needed(width_mm, cover_mm, link_dia_mm, d_mm):
    """Vertical legs across a beam: lateral spacing <= min(600, 0.75 d) and every bar within 150 mm."""
    inside = width_mm - 2.0 * cover_mm - link_dia_mm
    step = min(MAX_LATERAL_LEG_MM, 0.75 * d_mm, 2.0 * MAX_BAR_TO_LEG_MM)
    return max(2, int(math.ceil(inside / step - 1e-9)) + 1)


def beam_review(width_mm, height_mm, cover_mm, link_dia_mm, bar_dia_mm, spacing_mm, legs, fck_mpa,
                label=u'Beam'):
    """
    SMDSC 6.3 review of a beam's links. Returns (pitch to use, notes): a pitch over the maximum is
    brought down to it (and said so); the rest is reported for the designer.
    """
    width_mm, height_mm, cover_mm = float(width_mm), float(height_mm), float(cover_mm)
    link_dia_mm, bar_dia_mm, spacing_mm = float(link_dia_mm), float(bar_dia_mm), float(spacing_mm)
    notes = []
    d = effective_depth_mm(height_mm, cover_mm, link_dia_mm, bar_dia_mm)
    least, most = pitch_limits_mm(d, legs)
    pitch = spacing_mm
    if pitch > most + 1e-6:
        pitch = 25.0 * math.floor(most / 25.0)
        notes.append(u'{}: link pitch {:.0f} mm over the SMDSC 6.3 maximum min(300, 0.75d = {:.0f}): '
                     u'{:.0f} mm used.'.format(label, spacing_mm, 0.75 * d, pitch))
    elif pitch < least - 1e-6:
        notes.append(u'{}: link pitch {:.0f} mm under the SMDSC 6.3 minimum {:.0f} mm (room for the '
                     u'links along the beam).'.format(label, pitch, least))
    if link_dia_mm < MIN_LINK_DIA_MM:
        notes.append(u'{}: H{:.0f} links are under the preferred minimum H8 (SMDSC 6.3).'.format(
            label, link_dia_mm))
    ratio, need = link_ratio(legs, link_dia_mm, pitch, width_mm), rho_w_min(fck_mpa)
    if ratio < need - 1e-9:
        notes.append(u'{}: links H{:.0f} at {:.0f} give Asw/(s bw) = {:.3f} %, under the minimum '
                     u'{:.3f} % (EC2 9.2.2(5), SMDSC 6.3).'.format(label, link_dia_mm, pitch, 100 * ratio,
                                                                      100 * need))
    n_legs = legs_needed(width_mm, cover_mm, link_dia_mm, d)
    if n_legs > legs:
        notes.append(u'{}: {} vertical legs needed across {:.0f} mm (legs at <= min(600, 0.75d), every '
                     u'bar within 150 mm of a leg, SMDSC 6.3): add interior links.'.format(
                         label, n_legs, width_mm))
    if width_mm >= OPEN_LINK_WIDTH_MM:
        notes.append(u'{}: {:.0f} mm wide: open links with a top locking link may be used '
                     u'(SMDSC 6.3, Fig. 6.21).'.format(label, width_mm))
    if height_mm >= SIDE_BARS_DEPTH_MM:
        notes.append(u'{}: {:.0f} mm deep: side bars H16 at <= 250 mm added inside the links '
                     u'(SMDSC 6.3, EC2 7.3.3).'.format(label, height_mm))
    return pitch, notes


# ── Columns: IStructE SMDSC 6.4 / EC2 9.5 ────────────────────────────────────────────────────────

COLUMN_MAX_PITCH_MM = 400.0
COLUMN_REDUCTION = 0.6          # within the larger column dimension of a beam or slab, and at laps
COLUMN_MIN_BAR_MM = 16.0
COLUMN_MIN_RATIO, COLUMN_MAX_RATIO, COLUMN_MAX_RATIO_LAPS = 0.002, 0.04, 0.08


MC4_MIN_SLAB_MM = ((20.0, 200.0), (25.0, 250.0), (32.0, 300.0))


def mc4_min_slab_depth_mm(bar_dia_mm):
    """SMDSC MC4: the slab depth that lets column bars end in an L (detail A); thinner takes U-bars (B)."""
    for dia, depth in MC4_MIN_SLAB_MM:
        if bar_dia_mm <= dia + 1e-6:
            return depth
    return 10.0 * bar_dia_mm


def mc4_pairs(positions, along):
    """
    Opposite bars a detail-B U-bar joins: positions [(u, v)] of the faces whose bars are spaced
    along `along` ('u' or 'v'); returns sorted [(at, lo, hi)] — the position along that axis and the
    two across it — for every position with a bar on both faces.
    """
    k = 0 if along == 'u' else 1
    groups = {}
    for p in positions:
        groups.setdefault(round(p[k], 1), []).append(p[1 - k])
    return sorted((at, min(xs), max(xs)) for at, xs in groups.items() if len(xs) >= 2 and max(xs) - min(xs) > 1.0)


def column_link_dia_min_mm(bar_dia_mm, least_side_mm=None):
    """max(phi/4, 8) (6 for columns under 200 mm)."""
    floor = 6.0 if (least_side_mm is not None and least_side_mm < 200.0) else MIN_LINK_DIA_MM
    return max(bar_dia_mm / 4.0, floor)


def column_max_pitch_mm(bar_dia_mm, least_side_mm):
    """min(20 phi, least side, 400); the dense zones take 0.6 of it."""
    return min(20.0 * bar_dia_mm, least_side_mm, COLUMN_MAX_PITCH_MM)


def farthest_from_restraint_mm(n_bars_on_face, face_bar_pitch_mm, alternate_restrained):
    """How far the worst bar of a face is from a restrained one (corners always are)."""
    if n_bars_on_face <= 2:
        return 0.0
    if alternate_restrained:
        return face_bar_pitch_mm
    return ((n_bars_on_face - 1) // 2) * face_bar_pitch_mm


def column_review(geometry, cover_mm, link_dia_mm, bar_dia_mm, bar_count, per_face, spacing_mm,
                  dense_spacing_mm, densify, crossties, label=u'Column'):
    """
    SMDSC 6.4 review of a column. Returns (pitch, dense pitch, notes): pitches over the maxima are
    brought down to them (25 mm steps) and said so; the rest is reported for the designer.
    """
    notes = []
    if not geometry:
        return spacing_mm, dense_spacing_mm, notes
    cover_mm, link_dia_mm, bar_dia_mm = float(cover_mm), float(link_dia_mm), float(bar_dia_mm)
    spacing_mm, dense_spacing_mm = float(spacing_mm), float(dense_spacing_mm or spacing_mm)
    circle = geometry.get('shape') == 'circle'
    if circle:
        least = float(geometry['diameter_mm'])
        area = math.pi * least ** 2 / 4.0
    else:
        least = min(float(geometry['width_mm']), float(geometry['depth_mm']))
        area = float(geometry['width_mm']) * float(geometry['depth_mm'])
    most = column_max_pitch_mm(bar_dia_mm, least)
    dense_most = COLUMN_REDUCTION * most
    pitch, dense = spacing_mm, dense_spacing_mm
    if pitch > most + 1e-6:
        pitch = 25.0 * math.floor(most / 25.0)
        notes.append(u'{}: link pitch {:.0f} over the SMDSC 6.4 maximum min(20 phi, {:.0f}, 400) = {:.0f}: '
                     u'{:.0f} mm used.'.format(label, spacing_mm, least, most, pitch))
    if densify and dense > dense_most + 1e-6:
        dense = 25.0 * math.floor(dense_most / 25.0)
        notes.append(u'{}: link pitch next to beams and slabs {:.0f} over 0.6 x {:.0f}: {:.0f} mm used '
                     u'(SMDSC 6.4).'.format(label, dense_spacing_mm, most, dense))
    elif not densify:
        notes.append(u'{}: links at 0.6 x the pitch ({:.0f} mm) are needed within {:.0f} mm of beams '
                     u'and slabs (SMDSC 6.4): tick the dense zones (laps get them anyway).'.format(
                         label, dense_most, max(geometry.get('width_mm', least), geometry.get('depth_mm', least))))
    need_link = column_link_dia_min_mm(bar_dia_mm, least)
    if link_dia_mm < need_link - 1e-6:
        notes.append(u'{}: H{:.0f} links under max(phi/4, 8) = {:.0f} mm (SMDSC 6.4).'.format(
            label, link_dia_mm, need_link))
    if bar_dia_mm < (8.0 if least < 200.0 else COLUMN_MIN_BAR_MM):
        notes.append(u'{}: H{:.0f} main bars under the recommended H16 (SMDSC 6.4).'.format(label, bar_dia_mm))
    if bar_count < (6 if circle and least >= 200.0 else 4):
        notes.append(u'{}: {} bars: at least {} in a {} column (SMDSC 6.4).'.format(
            label, bar_count, 6 if circle else 4, u'circular' if circle else u'rectangular'))
    ratio = bar_count * math.pi * bar_dia_mm ** 2 / 4.0 / area
    if ratio < COLUMN_MIN_RATIO - 1e-9:
        notes.append(u'{}: {:.2f} % of steel, under 0.2 % of the section (plain column, EC2 12).'.format(
            label, 100 * ratio))
    elif ratio > COLUMN_MAX_RATIO + 1e-9:
        notes.append(u'{}: {:.2f} % of steel, over 4 % ({:.2f} % at laps against 8 %): check '
                     u'congestion or use couplers (SMDSC 6.4).'.format(label, 100 * ratio, 200 * ratio))
    if not circle:
        for face_mm, n in ((float(geometry['width_mm']), per_face[0]), (float(geometry['depth_mm']), per_face[1])):
            if n < 2:
                continue
            bar_pitch = (face_mm - 2.0 * (cover_mm + link_dia_mm) - bar_dia_mm) / (n - 1)
            worst = farthest_from_restraint_mm(n, bar_pitch, crossties)
            if worst > MAX_BAR_TO_LEG_MM + 1e-6:
                notes.append(u'{}: a bar on the {:.0f} mm face is {:.0f} mm from a restrained bar (> 150, '
                             u'SMDSC 6.4, Fig. 6.24): {}.'.format(
                                 label, face_mm, worst,
                                 u'restrain alternate bars with links' if not crossties else
                                 u'restrain every bar or close the bars up'))
            if bar_pitch > 300.0 + 1e-6:
                notes.append(u'{}: bars {:.0f} mm apart on the {:.0f} mm face, over the 300 mm preferred '
                             u'maximum (SMDSC 6.4).'.format(label, bar_pitch, face_mm))
    unique = []
    for n in notes:
        if n not in unique:
            unique.append(n)
    return pitch, dense, unique


STARTER_LINK_DIA_MM = 10.0       # SMDSC MF1 / MC1: H10-300, at least 3, round the starters in the base
STARTER_LINK_PITCH_MM = 300.0
STARTER_LINK_MIN_COUNT = 3


def starter_link_levels_mm(top_mm, bottom_mm, pitch_mm=STARTER_LINK_PITCH_MM, min_count=STARTER_LINK_MIN_COUNT):
    """Heights of the links holding column starters in a foundation, from the top down; [] if no room."""
    span = float(top_mm) - float(bottom_mm)
    if span < 50.0 * (min_count - 1):
        return []
    count = max(min_count, int(math.floor(span / pitch_mm + 1e-6)) + 1)
    step = min(float(pitch_mm), span / (count - 1))
    return [top_mm - k * step for k in range(count)]
