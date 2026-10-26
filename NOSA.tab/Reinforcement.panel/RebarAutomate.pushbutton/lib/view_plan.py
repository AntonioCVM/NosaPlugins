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
    # 1:25 first, as the slab sections (2026-10-26 audit, A9 on ST1 plan: at 1:50 its top and bottom bars, 91 mm apart
    # in plan, left no place for an indicator line 1 mm off them, and the plan was small on an empty sheet)
    'stair_plan': ((25, 50, 100), (260.0, 300.0)),
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
    return [(s, x, y) for s, x, y, _k in layout_choices([[wh] for wh in sizes], area, gap, reserved)]


def _spot(rects, w, h, area, gap):
    """The highest, then leftmost, free rectangle w x h among rects, or None."""
    ax0, ay0, ax1, ay1 = area
    xs = sorted(set([ax0] + [r[2] + gap for r in rects]))
    ys = sorted(set([ay1] + [r[1] - gap for r in rects]), reverse=True)
    for top in ys:
        for left in xs:
            rect = (left, top - h, left + w, top)
            if rect[2] > ax1 + 1e-6 or rect[1] < ay0 - 1e-6:
                continue
            if _free(rect, rects, gap - 1e-6):
                return rect
    return None


def layout_choices(options, area=A1_AREA, gap=GAP_MM, reserved=()):
    """
    layout() where each item may be drawn several ways (options: [[(w, h), ...]], preferred first): a sheet is filled
    before another is opened - an item takes the first of its ways that fits on a sheet already started (m6, user
    2026-10-25: S2 alone on sheet 4503 with room on 4502), and only then a new sheet in its preferred way. Returns
    [(sheet index, centre x, centre y, way)] in the input order.
    """
    ax0, ay0, ax1, ay1 = area
    order = sorted(range(len(options)), key=lambda i: (-options[i][0][0] * options[i][0][1], i))
    placed_out = [None] * len(options)
    sheets = [list(reserved)]
    for i in order:
        spot = None
        for sheet_index, rects in enumerate(sheets):
            for k, (w, h) in enumerate(options[i]):
                rect = _spot(rects, w, h, area, gap)
                if rect is not None:
                    spot = (sheet_index, rect, k)
                    break
            if spot:
                break
        if spot is None:
            if len(sheets[-1]) > len(reserved):
                sheets.append(list(reserved))       # an empty sheet is used, not left blank (one too big for it)
            w, h = options[i][0]
            spot = (len(sheets) - 1, (ax0, ay1 - h, ax0 + w, ay1), 0)
        sheet_index, rect, k = spot
        sheets[sheet_index].append(rect)
        placed_out[i] = (sheet_index, (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0, k)
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


def push_inside(boxes, area=A1_AREA, gap=GAP_MM / 2.0, fixed=()):
    """
    Viewports grown after the layout (the other members' 'SEE DRG' notes, written once every drawing has its number:
    2026-10-26 audit, B1-B2 ran 20 mm past the drawing area's left edge and onto B5-B6) moved sideways the least to
    lie inside the area and clear of one another and of the fixed boxes (the legends). boxes {key: (x0, y0, x1, y1)};
    returns {key: dx} for the boxes that move. Boxes that cannot all fit a row are left where they are.
    """
    def level(a, b):
        return a[1] < b[3] + gap and b[1] < a[3] + gap
    keys = sorted(boxes, key=lambda k: (boxes[k][0], k))
    x0 = dict((k, boxes[k][0]) for k in keys)
    width = dict((k, boxes[k][2] - boxes[k][0]) for k in keys)
    for i, k in enumerate(keys):
        lo = area[0]
        for j in keys[:i]:
            if level(boxes[j], boxes[k]):
                lo = max(lo, x0[j] + width[j] + gap)
        for f in fixed:
            if level(f, boxes[k]) and f[0] < boxes[k][0]:
                lo = max(lo, f[2] + gap)
        x0[k] = max(x0[k], lo)
    for i in range(len(keys) - 1, -1, -1):
        k = keys[i]
        hi = area[2]
        for j in keys[i + 1:]:
            if level(boxes[j], boxes[k]):
                hi = min(hi, x0[j] - gap)
        for f in fixed:
            if level(f, boxes[k]) and f[0] >= boxes[k][0]:
                hi = min(hi, f[0] - gap)
        if x0[k] + width[k] > hi:
            x0[k] = hi - width[k]
    ok = all(area[0] - 1e-6 <= x0[k] and x0[k] + width[k] <= area[2] + 1e-6 for k in keys)
    for i, k in enumerate(keys):
        for j in keys[i + 1:]:
            if level(boxes[j], boxes[k]) and x0[j] < x0[k] + width[k] + gap - 1e-6:
                ok = False
    if not ok:
        return {}
    return dict((k, x0[k] - boxes[k][0]) for k in keys if abs(x0[k] - boxes[k][0]) > 1e-6)


RC_SERIES = 4500      # NOSA protocol: 45xx RC details (user 2026-10-17: the reinforcement drawings start at 4500)


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


def arrange_block(mains, secs, gap=GAP_MM, beside=False):
    """
    One member's views as one compact block: its plans and elevations side by side (their datums level), its
    sections under them in rows no wider than the block - or, beside, in a column to their right, flush with their
    top (m6: the way that fits a sheet's free room). mains [(w, h, anchor)], secs [(w, h)]. Returns (width, height,
    [(x, y) centre from the block's top left, y down]) - mains then sections.
    """
    if beside and mains and secs:
        w0, h0, centres = arrange_block(mains, [], gap)
        col_w = max(w for w, _h in secs)
        y, out = 0.0, list(centres)
        for w, h in secs:
            out.append((w0 + gap + w / 2.0, y + h / 2.0))      # flush left in the column, one under another
            y += h + gap
        return w0 + gap + col_w, max(h0, y - gap), out
    lift = max([a for _w, _h, a in mains if a is not None] or [0.0])
    width = max([sum(w for w, _h, _a in mains) + gap * max(0, len(mains) - 1)] + [w for w, _h in secs] + [0.0])
    out, x, top_h = [], 0.0, 0.0
    for w, h, a in mains:
        y_top = lift - a if a is not None else 0.0
        out.append((x + w / 2.0, y_top + h / 2.0))
        top_h = max(top_h, y_top + h)
        x += w + gap
    y = top_h + gap if mains else 0.0
    row, row_w, row_h = [], 0.0, 0.0
    for w, h in list(secs) + [(None, None)]:
        if w is None or (row and row_w + gap + w > width + 1e-6):
            cx = 0.0            # flush left under the plans: sections one under another line up (user 2026-10-18, 4503)
            for rw, rh in row:
                out.append((cx + rw / 2.0, y + rh / 2.0))
                cx += rw + gap
            if row:
                y += row_h + gap
            if w is None:
                break
            row, row_w, row_h = [], 0.0, 0.0
        row.append((w, h))
        row_w = row_w + (gap if len(row) > 1 else 0.0) + w
        row_h = max(row_h, h)
    height = max(y - gap, top_h) if (mains or secs) else 0.0
    return width, height, out


def layout_packed(blocks, area=A1_AREA, gap=GAP_MM, reserved=()):
    """
    A drawing's members packed on as few sheets as they fit (user 2026-10-18: half the A1 was left empty when each
    member began a new line): each member a compact block (arrange_block), the blocks placed largest first in the
    highest, then leftmost, free spot (layout). blocks [(mains, secs)] as arrange_block takes them. Returns [(sheet
    index, centre x, centre y)], each block's mains then its sections, in the blocks' order.
    """
    parts, owner = [], []
    for b, (mains, secs) in enumerate(blocks):
        for m, s in _split_to_fit(list(range(len(mains))), list(range(len(secs))), mains, secs, area, gap, reserved):
            parts.append(([mains[i] for i in m], [secs[i] for i in s]))
            owner.append((b, m, s))
    ways = [_ways(mains, secs, gap) for mains, secs in parts]
    spots = layout_choices([[(w, h) for w, h, _c in way] for way in ways], area=area, gap=gap, reserved=reserved)
    placed = [([None] * len(mains), [None] * len(secs)) for mains, secs in blocks]
    for way, (sheet, cx, cy, k), (b, m, s) in zip(ways, spots, owner):
        w, h, centres = way[k]
        left, top = cx - w / 2.0, cy + h / 2.0
        at = [(sheet, left + x, top - y) for x, y in centres]
        for i, p in zip(m, at[:len(m)]):
            placed[b][0][i] = p
        for j, p in zip(s, at[len(m):]):
            placed[b][1][j] = p
    return [p for mains, secs in placed for p in mains + secs]


def _ways(mains, secs, gap):
    return [arrange_block(mains, secs, gap)] + ([arrange_block(mains, secs, gap, beside=True)] if mains and secs
                                                else [])


def _split_to_fit(m, s, mains, secs, area, gap, reserved):
    """
    A block that fits an empty sheet in none of its ways, cut into parts that do (2026-10-26 audit, A7 on 4516-4519:
    a slab's bottom and top plans side by side were 902 mm wide for 690 mm of drawing area and ran off the sheet):
    its plans one a part, the sections with the first; a lone view too big for any sheet is left whole.
    [(main indices, section indices)].
    """
    def fits(mm, ss):
        return any(_spot(list(reserved), w, h, area, gap) is not None
                   for w, h, _c in _ways([mains[i] for i in mm], [secs[i] for i in ss], gap))
    if fits(m, s) or len(m) + len(s) <= 1:
        return [(m, s)]
    if len(m) > 1:
        return _split_to_fit(m[:1], s, mains, secs, area, gap, reserved) + \
            [p for i in m[1:] for p in _split_to_fit([i], [], mains, secs, area, gap, reserved)]
    if m and s:
        return _split_to_fit(m, [], mains, secs, area, gap, reserved) + \
            _split_to_fit([], s, mains, secs, area, gap, reserved)
    return [(m, s)]


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


def member_of_view(view_name, titles):
    """'Slab S2 - Plan' -> 'S2', 'Beam B3-B4 - Elevation' -> 'B3-B4' (titles: the kinds' words); '' for others."""
    head = (view_name or u'').split(u' - ')[0]
    for title in titles:
        if head.startswith(title + u' '):
            return head[len(title) + 1:].strip()
    return u''


def member_prefix(view_name):
    """'Foundation F10 - Plan' -> 'Foundation F10 - ': what the names of that member's views start with."""
    head = (view_name or u'').split(u' - ')[0]
    return head + u' - ' if head else u''


def _split_mark(mark):
    """'C12' -> ('C', 12); None when the mark does not end in a number."""
    i = len(mark)
    while i > 0 and mark[i - 1].isdigit():
        i -= 1
    return (mark[:i], int(mark[i:])) if i < len(mark) else None


def holds(view_label, host_mark):
    """
    A view of member 'B3-B4' (a beam line), 'C1-C4' (a column stack: C2 and C3 too, 2026-10-25) or 'S2' holds the
    member marked host_mark.
    """
    if not host_mark:
        return False
    parts = view_label.split(u'-')
    if view_label == host_mark or host_mark in parts:
        return True
    if len(parts) == 2:
        a, b, m = _split_mark(parts[0]), _split_mark(parts[1]), _split_mark(host_mark)
        return bool(a and b and m and a[0] == b[0] == m[0] and a[1] <= m[1] <= b[1])
    return False


def column_stacks(items, tol_mm=50.0):
    """
    Columns standing on each other, one drawing each (user 2026-10-25: one continuous elevation, the same column
    through several floors or one changing size or shape between them). items: [(key, (x0, y0, x1, y1) plan box mm,
    z0, z1)]. A column goes on the stack whose top is at its base (within tol_mm) and whose top column's plan box
    overlaps its own. Returns [[key, ...]] bottom up, stacks in the order of their lowest column's item.
    """
    def overlap(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    stacks = []
    for key, box, z0, z1 in sorted(items, key=lambda it: it[2]):
        home = None
        for st in stacks:
            _k, top_box, _t0, top_z1 = st[-1]
            if abs(top_z1 - z0) <= tol_mm and overlap(top_box, box):
                home = st
                break
        if home is None:
            stacks.append([(key, box, z0, z1)])
        else:
            home.append((key, box, z0, z1))
    order = dict((it[0], i) for i, it in enumerate(items))
    stacks.sort(key=lambda st: min(order[k] for k, _b, _z0, _z1 in st))
    return [[k for k, _b, _z0, _z1 in st] for st in stacks]


def stack_label(marks):
    """The label of a drawing of members: 'C1' (one, or one Mark through every floor), else 'C1-C4'."""
    unique = []
    for m in marks:
        if m not in unique:
            unique.append(m)
    return unique[0] if len(unique) == 1 else u'{}-{}'.format(unique[0], unique[-1])


def sheet_names(base, labels_per_sheet, parts_per_sheet=None):
    """
    The names of a drawing's sheets (2026-10-24 audit, m5: 'Slabs reinforcement (2)'): one sheet keeps the base
    name, several are each named by the members on them - 'Slabs reinforcement - S1, S3', '... - S2'. A member on
    more than one sheet is named with what each holds of it (user 2026-10-26: 'S1 - Bottom', 'S1 - Top'):
    parts_per_sheet gives, beside each view's label, its part ('Bottom', or None for a section).
    """
    if len(labels_per_sheet) < 2:
        return [base] * len(labels_per_sheet)
    parts_per_sheet = parts_per_sheet or [[None] * len(labels) for labels in labels_per_sheet]
    sheets_of = {}
    for n, labels in enumerate(labels_per_sheet):
        for label in labels:
            if label:
                sheets_of.setdefault(label, set()).add(n)
    out = []
    for n, (labels, parts) in enumerate(zip(labels_per_sheet, parts_per_sheet)):
        seen, held = [], {}
        for label, part in zip(labels, parts):
            if not label:
                continue
            if label not in seen:
                seen.append(label)
            if part and part not in held.setdefault(label, []):
                held[label].append(part)
        names = [u'{} - {}'.format(label, u', '.join(held[label])) if len(sheets_of[label]) > 1 and held.get(label)
                 else label for label in seen]
        out.append(u'{} - {}'.format(base, u', '.join(names)) if names else base)
    return out


def view_part(view_name):
    """'Slab S1 - Bottom reinforcement' -> 'Bottom', 'Beam B3-B4 - Elevation' -> 'Elevation'; None for a section."""
    tail = (view_name or u'').split(u' - ', 1)[1] if u' - ' in (view_name or u'') else u''
    word = tail.split(u' ')[0] if tail else u''
    return None if not word or word == u'Section' else word


PART_ORDER = (u'Bottom', u'Top')      # a slab's bottom plan's sheet before its top plan's


def sheet_order(keys_per_sheet):
    """
    The order a drawing's sheets are numbered in (user 2026-10-26: S1..S4, each slab's bottom sheet then its top):
    keys_per_sheet [[(member label, part)]] in layout order -> [old sheet index] by member (C2 before C10), then part
    (PART_ORDER first), then layout order.
    """
    def member_key(label):
        mark = _split_mark(label or u'')
        return (mark[0], mark[1]) if mark else (label or u'', 0)

    def key(n):
        keys = keys_per_sheet[n]
        if not keys:
            return ((u'~', 0), len(PART_ORDER), n)
        return min((member_key(label), PART_ORDER.index(part) if part in PART_ORDER else len(PART_ORDER), n)
                   for label, part in keys)
    return sorted(range(len(keys_per_sheet)), key=key)


def boxes_touch(a, b, tol=50.0):
    """Two 3D boxes ((x0, y0, z0), (x1, y1, z1)), mm, meeting or within tol of each other."""
    return all(a[0][i] - tol <= b[1][i] and b[0][i] - tol <= a[1][i] for i in range(3))
