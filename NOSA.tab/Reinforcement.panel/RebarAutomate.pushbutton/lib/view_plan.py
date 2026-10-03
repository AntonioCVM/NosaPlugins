# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Create Views (T7.3): view scales and sheet layout. Pure, mm, no Revit.

Scales (user brief 2026-10-03): member cross-sections are details at 1:10 where they fit;
elevations, slab sections and plans take the smallest standard scale that fits the room the
view has on an A1 sheet — a tall continuous column may end at 1:50 or 1:100.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# kind -> (candidate scales, paper box (w, h) mm the view may take on the sheet)
SCALES = {
    'member_section': ((10, 20, 25), (200.0, 260.0)),
    'elevation': ((20, 25, 50, 100), (660.0, 300.0)),
    'column_elevation': ((20, 25, 50, 100), (300.0, 520.0)),
    'footing_section': ((10, 20, 25, 50), (320.0, 220.0)),
    'slab_section': ((50, 100), (660.0, 120.0)),
    'plan': ((50, 100, 200), (420.0, 360.0)),
    'stair_section': ((20, 25, 50), (420.0, 300.0)),
    'stair_plan': ((50, 100), (260.0, 300.0)),
}

# NOSA A1 QR titleblock: room for viewports, read from the template's own sheets (mm)
A1_AREA = (25.0, 25.0, 715.0, 575.0)
GAP_MM = 20.0
LABEL_MM = 14.0          # view title under each viewport


def choose_scale(kind, width_mm, height_mm):
    """Smallest candidate scale at which the view fits its paper box, else the largest."""
    scales, (box_w, box_h) = SCALES[kind]
    for scale in scales:
        if width_mm / scale <= box_w and height_mm / scale <= box_h:
            return scale
    return scales[-1]


def paper_size(width_mm, height_mm, scale):
    return width_mm / float(scale), height_mm / float(scale) + LABEL_MM


def _free(rect, placed, gap):
    x0, y0, x1, y1 = rect
    for a in placed:
        if x0 < a[2] + gap and a[0] < x1 + gap and y0 < a[3] + gap and a[1] < y1 + gap:
            return False
    return True


def layout(sizes, area=A1_AREA, gap=GAP_MM):
    """
    Top-left placement, largest first: [(sheet index, centre x, centre y)] in the input order,
    mm on the sheet. Each view takes the highest, then leftmost, free spot whose corner lies on
    the area's edge or next to a view already placed; when none fits, a new sheet starts.
    """
    ax0, ay0, ax1, ay1 = area
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][0] * sizes[i][1], i))
    placed_out = [None] * len(sizes)
    sheets = [[]]
    for i in order:
        w, h = sizes[i]
        spot = None
        for sheet_index, rects in enumerate(sheets):
            xs = sorted(set([ax0] + [r[2] + gap for r in rects]))
            ys = sorted(set([ay1] + [r[1] - gap for r in rects]), reverse=True)
            for top in ys:
                for left in xs:
                    rect = (left, top - h, left + w, top)
                    if rect[2] > ax1 + 1e-6 or rect[1] < ay0 - 1e-6:
                        continue
                    if _free(rect, rects, gap - 1e-6):
                        spot = (sheet_index, rect)
                        break
                if spot:
                    break
            if spot:
                break
        if spot is None:
            sheets.append([])
            rect = (ax0, ay1 - h, ax0 + w, ay1)
            spot = (len(sheets) - 1, rect)
        sheet_index, rect = spot
        sheets[sheet_index].append(rect)
        placed_out[i] = (sheet_index, (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)
    return placed_out


def next_sheet_numbers(existing, count, series=4000):
    """The next `count` free numbers of the series (4000 Construction details): '4002', ..."""
    taken = set(existing)
    out, n = [], series + 1
    while len(out) < count:
        if str(n) not in taken:
            out.append(str(n))
        n += 1
    return out
