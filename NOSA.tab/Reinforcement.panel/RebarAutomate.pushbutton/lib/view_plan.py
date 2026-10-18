# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Create Views (T7.3): view scales and sheet layout. Pure, mm, no Revit.

Scales (IStructE SMDSC 4th ed. 3.5, adopted 2026-10-07 over the 2026-10-03 brief): beam and column
sections 1:20, slab sections 1:25 when they fit (a mark over every cut bar, user 2026-10-10),
beam/column/wall elevations and slab details 1:50, general plans 1:100; a view that
does not fit its room on an A1 sheet takes the next preferred scale (BS 1192: 1:20, 1:50, 1:100,
1:200). 1:10 / 1:5 are kept for hand-picked details.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

# kind -> (candidate scales, paper box (w, h) mm the view may take on the sheet)
SCALES = {
    'member_section': ((20, 50), (200.0, 260.0)),
    'wall_section': ((20, 50), (200.0, 260.0)),     # one mark per cut set, like slabs (user 2026-10-11)
    'elevation': ((50, 100), (660.0, 300.0)),
    'column_elevation': ((50, 100), (300.0, 520.0)),
    'footing_section': ((20, 50), (320.0, 220.0)),
    'slab_section': ((25, 50, 100), (660.0, 120.0)),   # 1:25 first: room for a mark over every cut bar
    'plan': ((50, 100, 200), (420.0, 360.0)),
    'stair_section': ((20, 50), (420.0, 300.0)),
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


def coarser_scale(kind, scale):
    """The next candidate scale of this kind after `scale`, or None at the last one."""
    if kind not in SCALES:
        return None                      # a legend (a typical detail) keeps its own scale
    later = [s for s in SCALES[kind][0] if s > scale]
    return later[0] if later else None


def paper_size(width_mm, height_mm, scale):
    return width_mm / float(scale), height_mm / float(scale) + LABEL_MM


def _free(rect, placed, gap):
    x0, y0, x1, y1 = rect
    for a in placed:
        if x0 < a[2] + gap and a[0] < x1 + gap and y0 < a[3] + gap and a[1] < y1 + gap:
            return False
    return True


def layout(sizes, area=A1_AREA, gap=GAP_MM, reserved=()):
    """
    Top-left placement, largest first: [(sheet index, centre x, centre y)] in the input order,
    mm on the sheet. Each view takes the highest, then leftmost, free spot whose corner lies on
    the area's edge or next to a view already placed; when none fits, a new sheet starts.
    reserved: boxes every sheet keeps free (the legends' corner).
    """
    ax0, ay0, ax1, ay1 = area
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][0] * sizes[i][1], i))
    placed_out = [None] * len(sizes)
    sheets = [list(reserved)]
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
            sheets.append(list(reserved))
            rect = (ax0, ay1 - h, ax0 + w, ay1)
            spot = (len(sheets) - 1, rect)
        sheet_index, rect = spot
        sheets[sheet_index].append(rect)
        placed_out[i] = (sheet_index, (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)
    return placed_out


def layout_rows(streams, area=A1_AREA, gap=GAP_MM, reserved=()):
    """
    Views in reading order (user 2026-10-12: sections ordered, elevations of the same levels level with each other):
    streams [[(w, h, anchor)]], each stream starting a new line, its views left to right and on to the next line when
    the sheet is full. anchor: depth (mm) below the view's top of a datum shared by the line's views (the same model
    level in each elevation), lining them up; None puts the view's top on the line's top. Lines go down the sheet
    and on to a new sheet; reserved boxes (the legends' corner) are kept free. Returns [(sheet index, centre x,
    centre y)] in the streams' flattened order.
    """
    ax0, ay0, ax1, ay1 = area
    out = []
    sheet, top = 0, ay1

    def right_edge(y_top, y_bottom):
        edge = ax1
        for r in reserved:
            if y_bottom < r[3] + gap and r[1] - gap < y_top:
                edge = min(edge, r[0] - gap)
        return edge

    def line_height(items):
        lift = max([a for _w, _h, a in items if a is not None] or [0.0])
        return max((lift - a if a is not None else 0.0) + h for _w, h, a in items), lift

    for stream in streams:
        pending = list(stream)
        while pending:
            line = []
            for item in pending:
                trial = line + [item]
                height, _lift = line_height(trial)
                width = sum(w for w, _h, _a in trial) + gap * (len(trial) - 1)
                if line and ax0 + width > right_edge(top, top - height) + 1e-6:
                    break
                line = trial
            height, lift = line_height(line)
            if top - height < ay0 - 1e-6 and top < ay1 - 1e-6:
                sheet, top = sheet + 1, ay1                  # the line goes on to a new sheet
                continue
            x = ax0
            for w, h, a in line:
                y_top = top - (lift - a if a is not None else 0.0)
                out.append((sheet, x + w / 2.0, y_top - h / 2.0))
                x += w + gap
            top -= height + gap
            pending = pending[len(line):]
    return out


RC_SERIES = 4500       # NOSA protocol: 45xx RC details (user 2026-10-17: the reinforcement drawings start at 4500)


def next_sheet_numbers(existing, count, series=RC_SERIES):
    """The next `count` free numbers of the series from its first: '4500', '4501', ..."""
    taken = set(existing)
    out, n = [], series
    while len(out) < count:
        if str(n) not in taken:
            out.append(str(n))
        n += 1
    return out


SECTION_FRACTIONS = (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8)


def section_offsets(lo, hi):
    """
    Where to try a cut across a slab or base, nearest the middle first (user 2026-10-11: two real sections, A-A
    and B-B, clear of openings), between lo and hi along the other direction.
    """
    return [lo + (hi - lo) * f for f in SECTION_FRACTIONS]


TITLE_CHAR_MM = 3.0      # NOSA view title lettering on the sheet, per character
TITLE_EXTRA_MM = 10.0


def title_width_mm(view_name, title_on_sheet=u''):
    """Paper width a viewport's title takes (its Title on Sheet, else the view name), so titles never overlap."""
    text = title_on_sheet or view_name or u''
    return len(text) * TITLE_CHAR_MM + TITLE_EXTRA_MM


_PREFIXES = u'column C beam B floor S wall W foundation F pile_cap PC stairs ST'.split()
MARK_PREFIX = dict(zip(_PREFIXES[0::2], _PREFIXES[1::2]))     # kind -> GA mark prefix


def next_mark(prefix, taken):
    """The first free GA-style mark of a prefix: 'C' with C1-C3 and C21 taken -> 'C4' (user 2026-10-17)."""
    taken = set(m.strip().upper() for m in taken if m)
    n = 1
    while u'{}{}'.format(prefix, n).upper() in taken:
        n += 1
    return u'{}{}'.format(prefix, n)


def layout_blocks(blocks, area=A1_AREA, gap=GAP_MM, reserved=()):
    """
    A drawing of several columns (user 2026-10-17: elevations, sections and titles lined up): one block a member,
    its elevations side by side over its sections, centred under them. blocks [(mains [(w, h, anchor)], secs
    [(w, h)])]; the blocks of a line have their elevations' datums level and their sections' feet level (their titles
    in one line); lines go down the sheet and on to a new one, the reserved boxes kept free. Returns [(sheet index,
    centre x, centre y)], each block's mains then its sections, in the blocks' order.
    """
    ax0, ay0, ax1, ay1 = area

    def row_width(items):
        return sum(w for w, _h in items) + gap * max(0, len(items) - 1)

    def width(block):
        mains, secs = block
        return max(row_width([(w, h) for w, h, _a in mains]), row_width(secs))

    def right_edge(y_top, y_bottom):
        edge = ax1
        for r in reserved:
            if y_bottom < r[3] + gap and r[1] - gap < y_top:
                edge = min(edge, r[0] - gap)
        return edge

    def heights(line):
        mains = [m for b in line for m in b[0]]
        lift = max([a for _w, _h, a in mains if a is not None] or [0.0])
        top_h = max([(lift - a if a is not None else 0.0) + h for _w, h, a in mains] or [0.0])
        sec_h = max([h for b in line for _w, h in b[1]] or [0.0])
        return top_h, sec_h, lift

    out = {}
    sheet, top = 0, ay1
    pending = list(range(len(blocks)))
    while pending:
        line = []
        for k in pending:
            trial = line + [k]
            top_h, sec_h, _l = heights([blocks[i] for i in trial])
            total = top_h + (gap + sec_h if sec_h else 0.0)
            if line and ax0 + sum(width(blocks[i]) for i in trial) + gap * (len(trial) - 1) > \
                    right_edge(top, top - total) + 1e-6:
                break
            line = trial
        top_h, sec_h, lift = heights([blocks[i] for i in line])
        total = top_h + (gap + sec_h if sec_h else 0.0)
        if top - total < ay0 - 1e-6 and top < ay1 - 1e-6:
            sheet, top = sheet + 1, ay1
            continue
        x = ax0
        feet = top - top_h - gap - sec_h
        for k in line:
            mains, secs = blocks[k]
            bw = width(blocks[k])
            mx = x + (bw - row_width([(w, h) for w, h, _a in mains])) / 2.0
            places = []
            for w, h, a in mains:
                y_top = top - (lift - a if a is not None else 0.0)
                places.append((sheet, mx + w / 2.0, y_top - h / 2.0))
                mx += w + gap
            sx = x + (bw - row_width(secs)) / 2.0
            for w, h in secs:
                places.append((sheet, sx + w / 2.0, feet + h / 2.0))
                sx += w + gap
            out[k] = places
            x += bw + gap
        top -= total + gap
        pending = pending[len(line):]
    return [p for k in range(len(blocks)) for p in out[k]]
