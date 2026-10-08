# -*- coding: utf-8 -*-
"""
nosa_utils.corbels — in-situ column corbels, IStructE SMDSC 6.9 / Model Detail MCB1 (no welds). Pure Python, mm.

A corbel is described in its own frame: o out of the column face (0 at the face), a along the face (0
at the corbel's centre line), z absolute level. Main tension bars are horizontal U-loops round the
corbel's outer face whose legs cross the column and turn down a tension lap inside its far bars;
secondary horizontal U-bars carry at least half their area; compression bars follow the soffit into
the column with at least 1000 mm2 per metre width; two column links sit close to the corbel top.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

MAX_MAIN_DIA_MM = 16.0          # MCB1 without welds; larger bars need MCB2 (welded cross bar)
SECONDARY_SHARE = 0.5           # secondary horizontal bars: 50 % of the main tension area
COMPRESSION_MM2_PER_M = 1000.0  # compression bars: 1000 mm2 per metre width of corbel
MIN_GAP_MM = 25.0               # vertical gap between bar layers: max(25, phi)
TOP_LINK_OFFSETS_MM = (50.0, 125.0)   # the two column links close to the corbel top


def bar_area_mm2(dia_mm):
    return math.pi * float(dia_mm) ** 2 / 4.0


def layer_pitch_mm(dia_mm):
    """Centre-to-centre distance of two stacked layers: the bar plus max(25, phi) clear."""
    return float(dia_mm) + max(MIN_GAP_MM, float(dia_mm))


def compression_bar_count(width_mm, dia_mm):
    """Compression bars across a corbel width_mm wide: 1000 mm2/m, at least two."""
    need = COMPRESSION_MM2_PER_M * float(width_mm) / 1000.0
    return max(2, int(math.ceil(need / bar_area_mm2(dia_mm) - 1e-9)))


def secondary_loop_count(main_loops, main_dia_mm, secondary_dia_mm):
    """Secondary horizontal U-bars (two legs each) giving half the area of the main loops."""
    need = SECONDARY_SHARE * main_loops * bar_area_mm2(main_dia_mm)
    return max(1, int(math.ceil(need / bar_area_mm2(secondary_dia_mm) - 1e-9)))


def reach_at_mm(z_mm, corbel):
    """How far the corbel stands out at level z (0 under a sloped soffit's foot)."""
    top = corbel['top']
    z_face = top - corbel['depth_face']
    z_tip = top - corbel['depth_tip']
    if z_mm >= z_tip:
        return corbel['projection']
    if z_mm <= z_face or z_tip - z_face < 1e-6:
        return 0.0
    return corbel['projection'] * (z_mm - z_face) / (z_tip - z_face)


def even(lo, hi, n):
    if n <= 1:
        return [(lo + hi) / 2.0]
    return [lo + (hi - lo) * k / (n - 1.0) for k in range(n)]


def build(corbel, column, bars):
    """
    Bar polylines of one corbel in its frame (o, a, z), mm.
    corbel: top, projection, width, depth_face, depth_tip, cover.
    column: depth (face to far face), half_along (half the column face the corbel stands on), cover,
            link_dia, bar_dia, base (level of the column foot).
    bars: main_dia, main_loops, secondary_dia, compression_dia, lap_mm (tension lap of the main bars),
          anchorage_mm (compression anchorage of the compression bars).
    Returns {'main': [polyline], 'secondary': [polyline], 'compression': [polyline], 'top_links': [z],
             'notes': [...]}; a polyline is [(o, a, z), ...].
    """
    c = float(corbel['cover'])
    dm, ds, dc = float(bars['main_dia']), float(bars['secondary_dia']), float(bars['compression_dia'])
    notes = []
    if dm > MAX_MAIN_DIA_MM:
        notes.append(u'main bars H{:.0f} over 16 mm: SMDSC MCB2 asks for them welded to a cross bar or plate '
                     u'— detail the welds.'.format(dm))
    inside_col = column['cover'] + column['link_dia'] + column['bar_dia']
    o_far = -(column['depth'] - inside_col)                       # just inside the column's far bars
    y_main = min(corbel['width'] / 2.0 - c, column['half_along'] - inside_col) - dm / 2.0
    if y_main <= dm:
        notes.append(u'corbel {:.0f} mm wide: no room for the main loops inside its covers.'.format(corbel['width']))
        return {'main': [], 'secondary': [], 'compression': [], 'top_links': [], 'notes': notes}

    # main tension loops, from the top down
    main = []
    o_tip = corbel['projection'] - c - dm / 2.0
    z0 = corbel['top'] - c - dm / 2.0
    levels = [z0 - k * layer_pitch_mm(dm) for k in range(int(bars['main_loops']))]
    for z in levels:
        down = max(column['base'] + c, z - bars['lap_mm'])
        main.append([(o_far, y_main, down), (o_far, y_main, z), (o_tip, y_main, z),
                     (o_tip, -y_main, z), (o_far, -y_main, z), (o_far, -y_main, down)])
    notes.append(u'main loops round the corbel face need a large radius bend (SMDSC MCB1); keep the bearing '
                 u'at least max(phi, 0.75 cover) = {:.0f} mm inside them.'.format(max(dm, 0.75 * c)))

    # secondary horizontal U-bars, half the main area, spread down the rest of the depth
    secondary = []
    n_sec = secondary_loop_count(len(levels), dm, ds)
    hi = levels[-1] - layer_pitch_mm(max(dm, ds)) if levels else z0
    # lowest where the soffit still leaves half the projection (a level soffit: the bottom cover)
    z_face, z_tip = corbel['top'] - corbel['depth_face'], corbel['top'] - corbel['depth_tip']
    lo = max(z_face + (z_tip - z_face) / 2.0, z_tip - (z_tip - z_face)) + c + ds / 2.0
    n_fit = int(math.floor((hi - lo) / layer_pitch_mm(ds) + 1e-9)) + 1 if hi >= lo else 0
    for z in (even(lo, hi, min(n_sec, n_fit)) if n_fit > 1 else ([hi] if n_fit == 1 else [])):
        back = reach_at_mm(z - ds / 2.0, corbel) - c - ds / 2.0
        if back < c + ds:
            continue
        y = y_main
        secondary.append([(o_far, y, z), (back, y, z), (back, -y, z), (o_far, -y, z)])
    if len(secondary) < n_sec:
        notes.append(u'only {} of {} secondary U-bars fit inside the corbel.'.format(len(secondary), n_sec))

    # compression bars down the outer face and along the soffit into the column
    compression = []
    n_c = compression_bar_count(corbel['width'], dc)
    y_c = y_main - (dm + dc) / 2.0
    o_out = o_tip - (dm + dc) / 2.0
    z_top_c = corbel['top'] - c - dc / 2.0                       # beside the main loops, inside their backs
    z_tip_bottom = corbel['top'] - corbel['depth_tip'] + c + dc / 2.0
    run = corbel['projection']
    slope = (corbel['depth_face'] - corbel['depth_tip']) / run if run > 0 else 0.0
    def z_soffit(o):
        """Level of a compression bar along the soffit at o (the cover taken vertically)."""
        return corbel['top'] - corbel['depth_tip'] - slope * (corbel['projection'] - o) + c + dc / 2.0
    o_bend = o_out
    z_bend = max(z_tip_bottom, z_soffit(o_bend))
    pts = [(o_out, None, z_top_c), (o_bend, None, z_bend)]
    # on into the column for the compression anchorage, down the soffit's slope, inside its far bars
    remaining = float(bars['anchorage_mm'])
    if slope > 1e-6:
        o_face_z = z_soffit(0.0)
        length_out = math.hypot(o_bend, z_bend - o_face_z)
        dz_do = slope
        o_end = o_far if (o_bend - o_far) * math.sqrt(1 + dz_do ** 2) > remaining + length_out else \
            -remaining / math.sqrt(1 + dz_do ** 2)
        o_end = max(o_end, o_far)
        z_end = z_bend - slope * (o_bend - o_end)
        pts.append((o_end, None, z_end))
        used = math.hypot(o_end, z_end - o_face_z)
        if remaining > used + 1.0 and o_end <= o_far + 1.0:
            pts.append((o_end, None, max(column['base'] + c, z_end - (remaining - used))))
    else:
        o_end = max(o_far, -remaining)
        pts.append((o_end, None, z_bend))
        if remaining > -o_end + 1.0:
            pts.append((o_end, None, max(column['base'] + c, z_bend - (remaining + o_end))))
    if y_c > dc and z_top_c > z_bend:
        for y in even(-y_c, y_c, n_c):
            compression.append([(o, y, z) for o, _a, z in pts])
    else:
        notes.append(u'no room for the compression bars inside the main loops.')

    top_links = [corbel['top'] + d for d in TOP_LINK_OFFSETS_MM]
    return {'main': main, 'secondary': secondary, 'compression': compression, 'top_links': top_links,
            'notes': notes}
