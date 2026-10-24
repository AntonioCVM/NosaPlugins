# -*- coding: utf-8 -*-
"""
Where the calling-up of bars goes on a reinforcement drawing (IStructE SMDSC 4th ed. 3.3, 6.2.2), no Revit: on the
extension of a zone's indicator line, outside the member, else inside next to the zone; and the bar marks of
sections and elevations in rows outside the member, each over its bar, packed so no two touch and the
pointers stay as short and straight as they can. View coordinates in model mm; boxes (x0, y0, x1, y1).
"""


TOUCH = 1e-6


def overlap(a, b, gap=0.0):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


def exit_distance(point, direction, box):
    """How far from `point` (inside box) along unit `direction` the box ends; 0 when already outside."""
    best = None
    for axis, lo, hi in ((0, box[0], box[2]), (1, box[1], box[3])):
        d = direction[axis]
        if abs(d) < 1e-9:
            continue
        t = ((hi if d > 0 else lo) - point[axis]) / d
        best = t if best is None else min(best, t)
    return max(best or 0.0, 0.0)


def text_box(centre, along, length, height):
    """Box of a text `length` long along unit `along` (horizontal or vertical) and `height` across."""
    if abs(along[0]) >= abs(along[1]):
        return (centre[0] - length / 2.0, centre[1] - height / 2.0, centre[0] + length / 2.0, centre[1] + height / 2.0)
    return (centre[0] - height / 2.0, centre[1] - length / 2.0, centre[0] + height / 2.0, centre[1] + length / 2.0)


def place_inline(item, box, placed, gap, outside_gap, tries=12):
    """
    Calling-up of one zone (SMDSC 4th ed. 6.2.2): item {'a', 'b' (ends of the indicator line), 'length', 'height' (text)}.
    First on the common baseline just outside the member past either end (nearest edge first), so the
    calling-ups of a side line up; then pushed further out past texts already placed; then next to an end
    inside the member. Returns {'centre', 'end' ('a'|'b'), 'outside', 'box'} and appends the box to `placed`.
    """
    a, b = item['a'], item['b']
    run = (b[0] - a[0], b[1] - a[1])
    n = (run[0] ** 2 + run[1] ** 2) ** 0.5 or 1.0
    u = (run[0] / n, run[1] / n)
    ends = [('b', b, u), ('a', a, (-u[0], -u[1]))]
    ends.sort(key=lambda e: exit_distance(e[1], e[2], box))

    def at(p, out, start):
        c = (p[0] + out[0] * (start + item['length'] / 2.0), p[1] + out[1] * (start + item['length'] / 2.0))
        return c, text_box(c, out, item['length'], item['height'])

    def accept(name, c, bx, outside):
        placed.append(bx)
        return {'centre': c, 'end': name, 'outside': outside, 'box': bx}
    for name, p, out in ends:                                  # the baseline, both ends
        c, bx = at(p, out, exit_distance(p, out, box) + outside_gap)
        if not any(overlap(bx, q, gap) for q in placed):
            return accept(name, c, bx, True)
    for name, p, out in ends:
        # beside the baseline spot, a row across the line at a time: a calling-up pushed further out along the
        # same line has its leader run through the one before it (user 2026-10-12)
        across = (-out[1], out[0])
        step = item['height'] + gap
        c0, _bx = at(p, out, exit_distance(p, out, box) + outside_gap)
        # up to 8 rows: clear of a column cut above a base before going further out (user 2026-10-17, F10)
        for k in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7, 8, -8):
            c = (c0[0] + across[0] * step * k, c0[1] + across[1] * step * k)
            bx = text_box(c, out, item['length'], item['height'])
            if not any(overlap(bx, q, gap) for q in placed):
                return accept(name, c, bx, True)
    for name, p, out in ends:                                  # further out
        start = exit_distance(p, out, box) + outside_gap
        for _ in range(tries):
            c, bx = at(p, out, start)
            hits = [q for q in placed if overlap(bx, q, gap)]
            if not hits:
                return accept(name, c, bx, True)
            far = max(abs((q[2] if out[0] > 0 else q[0]) - p[0]) * abs(out[0]) +
                      abs((q[3] if out[1] > 0 else q[1]) - p[1]) * abs(out[1]) for q in hits)
            start = far + gap
    for name, p, out in ends:                                  # inside, next to the zone
        c, bx = at(p, out, gap)
        if not any(overlap(bx, q, gap) for q in placed):
            return accept(name, c, bx, False)
    c, bx = at(b, u, gap)
    return accept('b', c, bx, False)


def segment_box(p, q, pad):
    """A line's box, `pad` round it."""
    return (min(p[0], q[0]) - pad, min(p[1], q[1]) - pad, max(p[0], q[0]) + pad, max(p[1], q[1]) + pad)


def place_beside(junction, u, length, height, box, placed, obstacles, gap, off, lift, rows=4):
    """
    A plan's calling-up inside the member beside its zone (user 2026-10-17): a level text next to where the
    indicator line (unit `u`) crosses the typical bar, past the leader's landing `off` along the line and `lift`
    off it, clear of texts placed and of the lines in `obstacles`. Returns (centre, sign along u, side across) or
    None; appends the box to `placed`.
    """
    nrm = (-u[1], u[0])
    hx, hy = length / 2.0, height / 2.0
    ext_n = abs(nrm[0]) * hx + abs(nrm[1]) * hy
    ext_u = abs(u[0]) * hx + abs(u[1]) * hy
    # nearest first: a row off the line, then slid along it a text at a time (past the other direction's typical
    # bar, user 2026-10-18 S1), then further off
    steps = sorted(((k, j) for k in range(rows) for j in range(rows)), key=lambda kj: (kj[0] + kj[1], kj[1]))
    for k, j in steps:
        for along in (1.0, -1.0):
            for side in (1.0, -1.0):
                t_n = side * (ext_n + lift + k * (height + gap))
                t_u = along * (off + ext_u + gap + j * (2.0 * ext_u + gap))
                c = (junction[0] + nrm[0] * t_n + u[0] * t_u, junction[1] + nrm[1] * t_n + u[1] * t_u)
                bx = (c[0] - hx, c[1] - hy, c[0] + hx, c[1] + hy)
                if bx[0] < box[0] or bx[1] < box[1] or bx[2] > box[2] or bx[3] > box[3]:
                    continue
                if any(overlap(bx, q, gap) for q in placed) or any(overlap(bx, q) for q in obstacles):
                    continue
                placed.append(bx)
                return c, along, side
    return None


def align_rows(items, box, gap, outside, placed=(), lift=0.0, obstacles=(), neighbours=(), native=False,
               blockers=()):
    """
    _align_rows_once (below); for Revit's own leaders, then a calling-up caught in a crossing tried on the member's
    other side, kept when fewer lines cross (2026-10-24 review: S1's last crossings went once two texts swapped
    sides). Sides a calling-up is given ('side') are kept.
    """
    _dump_layout(items, box, gap, outside, placed, lift, obstacles, neighbours, native, blockers)
    args = (box, gap, outside)
    kw = dict(lift=lift, obstacles=obstacles, neighbours=neighbours, native=native, blockers=blockers)
    best = _align_rows_once(items, *args, placed=list(placed), **kw)
    if not native:
        return best
    score = _crossing_score(best, blockers)
    tried = set()
    for _round in range(2):
        if not score:
            break
        better = False
        for key in _crossing_keys(best, blockers):
            if key in tried or items[key].get('side') or key not in best:
                continue
            tried.add(key)
            trial_items = dict(items)
            trial_items[key] = dict(items[key], side='left' if best[key]['side'] == 'right' else 'right')
            trial = _align_rows_once(trial_items, *args, placed=list(placed), **kw)
            n = _crossing_score(trial, blockers)
            if n < score:
                best, score, better = trial, n, True
                items = trial_items
        if not better:
            break
    return best


def _crossing_score(laid, blockers):
    hits = sum(1 for r in laid.values() for seg in zip(r['path'], r['path'][1:]) for b in blockers if _crosses(seg, b))
    return path_crossings(laid) + hits


def _crossing_keys(laid, blockers):
    """The calling-ups whose lines cross another's or a blocker."""
    segs = [(k, seg) for k, r in laid.items() for seg in zip(r['path'], r['path'][1:])]
    out = []
    for i, (k1, s1) in enumerate(segs):
        if any(_crosses(s1, b) for b in blockers) and k1 not in out:
            out.append(k1)
        for k2, s2 in segs[i + 1:]:
            if k1 != k2 and _crosses(s1, s2):
                for k in (k1, k2):
                    if k not in out:
                        out.append(k)
    return out


def _align_rows_once(items, box, gap, outside, placed=(), lift=0.0, obstacles=(), neighbours=(), native=False,
                     blockers=()):
    """
    Calling-ups of a plan's or a wall elevation's zones as Arup's detailing manual (R. Whittle, 1.5.1) and the SMDSC
    4th ed. working drawings draw them (user 2026-10-18): every text level, written on a line that underlines it;
    that line leaves the zone's indicator line square to the member's side - from its end for a level indicator line,
    from a point along it for an upright one - and runs straight out to a column of texts beside the member. All
    those lines are level and at different heights, so none crosses another and each text is read back to its zone.
    items {id: {'a', 'b' (indicator line ends), 'length', 'height' (text), 'at' (optional: where along an upright
    line to leave it)}}. Returns {id: {'centre' (text), 'path' ([points] from the indicator line to the far end of
    the underline), 'box', 'side'}}; the boxes are added to placed.
    native (Phase 12, user 2026-10-18): the lines are Revit's own tag leaders, one elbow each, always square - the
    path is [leader end on the bar or indicator line, elbow straight across from it at the text's height (left out
    when level with it), the text's near edge]; where along a level line its leader leaves is chosen with the rows
    so that no two leaders cross, and then that as few as can cross blockers (segments: the view's dimension and
    indicator lines - 2026-10-24 review: leaders across other zones' indicator lines).
    """
    placed = list(placed)
    sides = {}
    level = {}
    lines = dict((k, (it['a'], it['b'])) for k, it in items.items())

    def crossings(key, start, side):
        # the other items' indicator lines a level run from start out to the member's side would cross
        run = (start, (box[0] if side == 'left' else box[2], start[1]))
        return sum(1 for k, seg in lines.items() if k != key and _crosses(run, seg))

    # twice a column's width: section heads and grids push a column out before it stands (S1, Revit 2026)
    reach = 2.0 * (outside + max([it['length'] for it in items.values()] or [0.0]))
    blocked = {'left': any(overlap((box[0] - reach, box[1], box[0], box[3]), q) for q in neighbours),
               'right': any(overlap((box[2], box[1], box[2] + reach, box[3]), q) for q in neighbours)}

    def pick(key, it, left, right, nearer):
        # the side whose column is clear of the other members drawn (2026-10-18, Revit 2026: S3's calling-ups
        # stood on the next slab), then whose line crosses fewer of the others' (W10), the nearer one when even
        if it.get('side'):
            return it['side']
        if blocked['left'] != blocked['right']:
            return 'right' if blocked['left'] else 'left'
        cl, cr = crossings(key, left, 'left'), crossings(key, right, 'right')
        if cl == cr:
            return nearer
        return 'left' if cl < cr else 'right'

    def is_level(it):
        # a bar seen as little more than a point (a diagonal marked where it is) is called up as a level one: an
        # upright line from it ran metres along no bar (S1, 2026-10-18)
        a, b = it['a'], it['b']
        short = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 < 2.0 * it['height']
        return short or abs(b[0] - a[0]) >= abs(b[1] - a[1])

    for key, it in items.items():
        a, b = it['a'], it['b']
        if is_level(it):
            lo, hi = (a, b) if a[0] <= b[0] else (b, a)
            level[key] = (lo, hi, pick(key, it, lo, hi, 'right' if box[2] - hi[0] <= lo[0] - box[0] else 'left'))
    risers = {}
    for key, (lo, hi, side) in level.items():
        # zones end to end on one row: the inner one's line would run out over the outer one's, so it rises square
        # from its own middle to a height of its own (2026-10-18: two such lines read as one closed box)
        y, h = lo[1], items[key]['height']
        if hi[0] - lo[0] < 2.0 * h:
            continue                         # a bar marked at a point jogs beside the member, it does not rise
        for other, (olo, ohi, oside) in level.items():
            if other == key or oside != side or abs(olo[1] - y) > h / 2.0:
                continue
            if (side == 'left' and ohi[0] <= lo[0] + TOUCH) or (side == 'right' and olo[0] >= hi[0] - TOUCH):
                risers[key] = _riser(lo, hi, side, h, gap, box, obstacles)
                break
    for key, it in items.items():
        a, b = it['a'], it['b']
        if key in level:
            lo, hi, side = level[key]
            end = hi if side == 'right' else lo
            span, under = None, end[1]
            if key in risers:
                end, under = risers[key]
        else:
            lo, hi = (a, b) if a[1] <= b[1] else (b, a)
            x = (a[0] + b[0]) / 2.0
            span = (lo[1], hi[1])
            under = min(max(it.get('at', (lo[1] + hi[1]) / 2.0), lo[1]), hi[1])
            side = pick(key, it, (x, under), (x, under), 'right' if box[2] - x <= x - box[0] else 'left')
            end = (x, under)
        sides.setdefault(side, []).append((key, end, span, under + it['height'] / 2.0 + lift))

    def lay(side, rows, desired, legs=None):
        # one side's texts in the order of rows, their lines from the indicator lines or bars
        keys = [r[0] for r in rows]
        heights = [items[k]['height'] for k in keys]
        at = pack(desired, heights, gap)
        reach = max(items[k]['length'] for k in keys)
        lo_band = min(c - h / 2.0 for c, h in zip(at, heights))
        hi_band = max(c + h / 2.0 for c, h in zip(at, heights))
        start = outside
        for _ in range(12):
            x0 = box[2] + start if side == 'right' else box[0] - start - reach
            hits = [q for q in placed if overlap((x0, lo_band, x0 + reach, hi_band), q, gap)]
            if not hits:
                break
            start = (max(q[2] for q in hits) - box[2] if side == 'right' else box[0] - min(q[0] for q in hits)) + gap
        sign = 1.0 if side == 'right' else -1.0
        res = {}
        near = box[2] + start if side == 'right' else box[0] - start
        edge = box[2] if side == 'right' else box[0]
        # lines packed off their own height jog square in the gap beside the member, each at its own distance, in
        # the order that keeps them from crossing: of those going up the highest jogs nearest the member, of
        # those going down the lowest (2026-10-18: jogs sharing one upright read as one line)
        if native:
            return lay_native(side, rows, at, near, sign, legs or {})
        lifted = [(r[0], r[1][1], c - items[r[0]]['height'] / 2.0 - lift) for r, c in zip(rows, at)
                  if r[2] is None and r[0] not in risers]
        # an upright bar whose row is past its end leaves from that end and jogs in the gap as the others do: run
        # on along its line it crossed the others' lines where there is no bar (S1, 2026-10-18)
        for r, c in zip(rows, at):
            u = c - items[r[0]]['height'] / 2.0 - lift
            if r[2] is not None and not (r[2][0] - 1e-6 <= u <= r[2][1] + 1e-6):
                lifted.append((r[0], min(max(u, r[2][0]), r[2][1]), u))
        ups = sorted([k for k, y, u in lifted if u > y + 1e-6], key=lambda k: -dict((a, y) for a, y, _u in lifted)[k])
        downs = sorted([k for k, y, u in lifted if u < y - 1e-6], key=lambda k: dict((a, y) for a, y, _u in lifted)[k])
        ys = dict((a, (y, u)) for a, y, u in lifted)
        order = jog_order(ups + downs, ys)
        jog_at = {}
        prev = 0.0
        for i, k in enumerate(order):
            base = (i + 1.0) / (len(order) + 1.0)
            y0, y1 = sorted(ys[k])
            # clear of what is drawn in the gap (a section mark's arrow beside a column, 2026-10-18), but always
            # beyond the jog before it, so the order that keeps the lines from crossing holds (S1, 2026-10-18)
            room = 1.0 - (len(order) - i) * 0.02
            fs = [f for f in [base] + [j / 40.0 for j in range(1, 40)] if prev + 0.01 <= f <= room] or [base]
            best = None
            for f in sorted(fs, key=lambda q: abs(q - base)):
                x = edge + sign * start * f
                over = sum(min(q[3], y1) - max(q[1], y0) for q in placed
                           if q[0] - gap / 4.0 < x < q[2] + gap / 4.0 and q[1] < y1 and q[3] > y0)
                if best is None or over < best[0] - 1e-6:
                    best = (over, x, f)
                if over <= 0.0:
                    break
            jog_at[k] = best[1]
            prev = best[2]
        for (key, end, span, _w), c in zip(rows, at):
            n, h = items[key]['length'], items[key]['height']
            u = c - h / 2.0 - lift                    # the underline's height
            far = (near + sign * n, u)
            if key in risers:
                path = [end, (end[0], u), far]
            elif span is None:
                if abs(u - end[1]) < 1e-6:
                    path = [end, far]
                else:                                 # packed off its line: a square jog in the gap beside the member
                    jog = jog_at.get(key, near - sign * min(outside, start) / 2.0)
                    path = [end, (jog, end[1]), (jog, u), far]
            else:
                foot = (end[0], min(max(u, span[0]), span[1]))
                if abs(foot[1] - u) < 1e-6:
                    path = [foot, far]
                else:
                    jog = jog_at.get(key, near - sign * min(outside, start) / 2.0)
                    path = [foot, (jog, foot[1]), (jog, u), far]
            centre = (near + sign * n / 2.0, c)
            bx = (min(near, far[0]), c - h / 2.0, max(near, far[0]), c + h / 2.0)
            res[key] = {'centre': centre, 'path': path, 'box': bx, 'side': side}
        return res

    def lay_native(side, rows, at, near, sign, legs):
        res = {}
        for (key, end, span, _w), c in zip(rows, at):
            n, h = items[key]['length'], items[key]['height']
            u = c                                     # a tag's leader meets its text at the text's middle
            text = (near, u)
            if key in risers:
                start = end
            elif span is None:
                lo_, hi_, _s = level[key]
                a_, b_ = (hi_, lo_) if side == 'right' else (lo_, hi_)     # from the end nearer the texts inward
                f = legs.get(key, 0.0)
                start = (a_[0] + (b_[0] - a_[0]) * f, a_[1] + (b_[1] - a_[1]) * f)
            else:
                start = (end[0], min(max(u, span[0]), span[1]))
            path = [start, text] if abs(start[1] - u) < 1e-6 else [start, (start[0], u), text]
            far = (near + sign * n, u)
            bx = (min(near, far[0]), c - h / 2.0, max(near, far[0]), c + h / 2.0)
            res[key] = {'centre': (near + sign * n / 2.0, c), 'path': path, 'box': bx, 'side': side}
        return res

    out = {}
    for side, rows in sides.items():
        rows.sort(key=lambda r: r[3])
        # the rows' heights stay where they are wanted; which text takes which may change: a line rising
        # along its bar to its row runs level across the whole gap and cut through another's jog (S1,
        # 2026-10-18), so rows swap while that leaves fewer lines crossing
        desired = [r[3] + 1e-9 * i for i, r in enumerate(rows)]
        legs = {}

        def cost(laid):
            # first no two lines crossing, then the least run along no bar: an upright bar's leader carried past
            # its end to a row far off (S1, 2026-10-18)
            over = 0.0
            for r in rows:
                if r[2] is not None:
                    y = laid[r[0]]['path'][-1][1] if native else laid[r[0]]['path'][0][1]
                    over += max(0.0, r[2][0] - y, y - r[2][1])
            hits = 0
            for r_ in laid.values():
                for seg in zip(r_['path'], r_['path'][1:]):
                    hits += sum(1 for b in blockers if _crosses(seg, b))
            n = path_crossings(laid)       # two leaders crossing read worse than a leader over a dimension
            return (n, n + hits, round(over, 3))

        def search(rows, legs):
            # moves while they leave fewer crossings: where each level leader leaves its line, then rows swapped
            # or taken out and put back elsewhere
            best = lay(side, rows, desired, legs)
            best_c = cost(best)
            for _ in range(len(rows) * len(rows)):
                if best_c == (0, 0, 0.0):
                    break
                better = False
                if native:
                    for key in [r[0] for r in rows if r[2] is None and r[0] not in risers]:
                        for f in LEG_AT:
                            trial_legs = dict(legs)
                            trial_legs[key] = f
                            laid = lay(side, rows, desired, trial_legs)
                            c = cost(laid)
                            if c < best_c:
                                legs, best, best_c, better = trial_legs, laid, c, True
                for i in range(len(rows)):
                    for j in range(len(rows)):
                        if i == j:
                            continue
                        trial = list(rows)
                        if i < j:
                            trial[i], trial[j] = trial[j], trial[i]
                        else:
                            trial.insert(j, trial.pop(i))
                        laid = lay(side, trial, desired, legs)
                        c = cost(laid)
                        if c < best_c:
                            rows, best, best_c, better = trial, laid, c, True
                if not better:
                    break
            return rows, legs, best, best_c

        rows, legs, best, best_c = search(rows, legs)
        if native and best_c[0] and len(rows) > 3:
            # still crossing: the moves above stop where no single one helps (S1, 2026-10-24) - shake a few rows
            # and search again, keeping what crosses less; seeded, so a drawing comes out the same every run
            import random
            rng = random.Random(len(rows))
            for _restart in range(RESTARTS):
                trial = list(rows)
                for _k in range(3):
                    i, j = rng.randrange(len(trial)), rng.randrange(len(trial))
                    trial[i], trial[j] = trial[j], trial[i]
                t_rows, t_legs, t_best, t_c = search(trial, dict(legs))
                if t_c < best_c:
                    rows, legs, best, best_c = t_rows, t_legs, t_best, t_c
                if not best_c[0]:
                    break
        for key in [r[0] for r in rows]:
            placed.append(best[key]['box'])
            out[key] = best[key]
    return out


LEG_AT = (0.0, 0.1, 0.25, 0.4, 0.6, 0.75, 0.9, 1.0)   # where along a level line a native leader may leave it
RESTARTS = 6      # shaken restarts of a side's search while its native leaders still cross


def _dump_layout(items, box, gap, outside, placed, lift, obstacles, neighbours, native, blockers):
    """With NOSA_LAYOUT_DUMP set to a folder, each layout's input as JSON there, to replay it outside Revit."""
    import os
    folder = os.environ.get('NOSA_LAYOUT_DUMP')
    if not folder:
        try:
            from System import Environment          # IronPython's os.environ is a copy taken at start-up
            folder = Environment.GetEnvironmentVariable('NOSA_LAYOUT_DUMP')
        except Exception:
            folder = None
    if not folder:
        return
    try:
        import json
        name = os.path.join(folder, 'layout_{}_{}.json'.format(len(items), int(abs(box[0]) + abs(box[1])) % 100000))
        data = {'items': dict((repr(k), v) for k, v in items.items()), 'box': box, 'gap': gap, 'outside': outside,
                'placed': list(placed), 'lift': lift, 'obstacles': list(obstacles), 'neighbours': list(neighbours),
                'native': native, 'blockers': list(blockers)}
        with open(name, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def path_crossings(laid):
    """How many pairs of segments of different calling-ups' lines cross."""
    segs = [(k, seg) for k, r in laid.items() for seg in zip(r['path'], r['path'][1:])]
    return sum(1 for i, (k1, s1) in enumerate(segs) for k2, s2 in segs[i + 1:] if k1 != k2 and _crosses(s1, s2))


def jog_order(keys, ys):
    """
    The order, nearest the member first, of the square jogs of lines packed off their own height (ys {key: (from,
    to)}) that keeps them from crossing: a line whose upright spans another's start runs beyond it, and one whose
    upright spans another's end runs inside it. keys gives the order to keep where nothing forces one.
    """
    outer = dict((k, set()) for k in keys)          # outer[k]: the jogs k must stand beyond
    for a in keys:
        lo, hi = sorted(ys[a])
        for b in keys:
            if a == b:
                continue
            if lo < ys[b][0] < hi:
                outer[a].add(b)                      # b's run in from its start crosses a's upright unless a is out
            if lo < ys[b][1] < hi:
                outer[b].add(a)                      # b's run out from its end crosses a's upright unless b is out
    done, out = set(), []
    while len(out) < len(keys):
        free = [k for k in keys if k not in done and not (outer[k] - done)]
        if not free:                                 # no order keeps every line clear: the fewest crossings
            free = sorted([k for k in keys if k not in done], key=lambda k: len(outer[k] - done))[:1]
        out.append(free[0])
        done.add(free[0])
    return out


def _crosses(s, t):
    """Two segments crossing through each other (touching at an end is not crossing)."""
    (a, b), (c, d) = s, t

    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


def _riser(lo, hi, side, h, gap, box, obstacles):
    """
    Where the line of a zone shut in on its row by another rises from, and the height it runs out at: off the
    zone's middle (its typical bar is there, 2026-10-18), nearer the column, and clear of the bars seen in the view
    (obstacles: segments), so neither the rise nor the run lies along a bar. Returns ((x, y), height).
    """
    y = lo[1]
    clear = 0.6 * h
    span = hi[0] - lo[0]
    order = (0.25, 0.15, 0.35, 0.1, 0.4)
    xs = [(lo[0] + q * span) if side == 'left' else (hi[0] - q * span) for q in order]
    uprights = [o for o in obstacles if abs(o[1][0] - o[0][0]) < abs(o[1][1] - o[0][1])]
    levels = [o for o in obstacles if abs(o[1][0] - o[0][0]) >= abs(o[1][1] - o[0][1])]

    def along_upright(x, y0, y1):
        for (p, q) in uprights:
            ox = (p[0] + q[0]) / 2.0
            if abs(ox - x) < clear and min(p[1], q[1]) < y1 and max(p[1], q[1]) > y0:
                return True
        return False

    def along_level(x, u):
        x0, x1 = (box[0], x) if side == 'left' else (x, box[2])
        for (p, q) in levels:
            oy = (p[1] + q[1]) / 2.0
            if abs(oy - u) < clear and min(p[0], q[0]) < x1 and max(p[0], q[0]) > x0:
                return True
        return False

    step = 0.5 * (h + gap)
    for k in range(2, 12):
        u = y + k * step
        for x in xs:
            if not along_upright(x, y, u) and not along_level(x, u):
                return (x, y), u
    return (xs[0], y), y + 2 * step


def _crosses_box(seg, box):
    """A segment with a part inside the box (Liang-Barsky)."""
    (x0, y0), (x1, y1) = seg
    dx, dy = x1 - x0, y1 - y0
    lo, hi = 0.0, 1.0
    for p, q in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            lo = max(lo, r)
        else:
            hi = min(hi, r)
        if lo > hi:
            return False
    return hi - lo > 1e-9


def _figure(lo, hi, at, vertical, m, text, height):
    """The box of a dimension's figure at m along it: over a level dimension's line, left of an upright one's."""
    if vertical:
        return (at - height, m - text / 2.0, at, m + text / 2.0)
    return (m - text / 2.0, at, m + text / 2.0, at + height)


def clear_offset(lo, hi, c, vertical, offsets, boxes, segments, half, text=0.0, own=(), height=None):
    """
    Where a dimension along [lo, hi] beside a line at c (x for a vertical one, y else) goes: the first of offsets
    (signed, from c) whose band (the dimension line +/- half) meets no box and has no segment running along it, and
    whose figure (text long, height high, in the middle) no segment crosses, own (the bar measured) included. When
    none is clear, the one with fewest clashes (S2, Revit 2026: every offset clashed and the first was taken, its
    figure on a zone's line).
    """
    height = 2.0 * half if height is None else height
    best, best_n = c + offsets[0], None
    mid = (lo + hi) / 2.0
    for off in offsets:
        at = c + off
        band = (at - half, lo, at + half, hi) if vertical else (lo, at - half, hi, at + half)
        n = sum(1 for q in boxes if overlap(band, q))
        if text:
            words = _figure(lo, hi, at, vertical, mid, text, height)
            n += sum(1 for seg in list(segments) + list(own) if _crosses_box(seg, words))
        for (p, q) in segments:
            sb = (min(p[0], q[0]), min(p[1], q[1]), max(p[0], q[0]), max(p[1], q[1]))
            if not overlap(band, sb):
                continue
            along = abs(q[1] - p[1]) > abs(q[0] - p[0]) if vertical else abs(q[0] - p[0]) > abs(q[1] - p[1])
            if along:
                n += 1                   # a line running inside the band: the dimension would sit on it
        if n == 0:
            return at
        if best_n is None or n < best_n:
            best, best_n = at, n
    return best


def clear_along(lo, hi, at, vertical, segments, height, text):
    """
    Where along a dimension [lo, hi] at at its figure (text long, height high, on its side) is crossed by no
    segment: the middle when clear, else the clear spot nearest it; None when there is none.
    """
    mid = (lo + hi) / 2.0
    room = (hi - lo - text) / 2.0
    if room <= 0:
        return None
    for k in range(0, 9):
        for sign in ((1,) if k == 0 else (-1, 1)):
            m = mid + sign * room * k / 8.0
            words = _figure(lo, hi, at, vertical, m, text, height)
            if not any(_crosses_box(seg, words) for seg in segments):
                return m
    return None


def stack(box, side, lines, gap):
    """
    Centres of texts stacked top down in one calling-up's box, each flush with the member's side of it (Arup's
    detailing manual: two zones' calling-ups with ALT or STG between them, on one underline). lines [(length,
    height)]; the box is sum(heights) + gap between them high.
    """
    sign = 1.0 if side == 'right' else -1.0
    near = box[0] if side == 'right' else box[2]
    y, out = box[3], []
    for n, h in lines:
        out.append((near + sign * n / 2.0, y - h / 2.0))
        y -= h + gap
    return out


def pack(desired, widths, gap):
    """
    Centres along a line, in the order of `desired`, no two closer than half their widths plus gap, each
    as near its desired place as it can be: isotonic regression (pool adjacent violators) of the desired
    places less the room the ones before need.
    """
    order = sorted(range(len(desired)), key=lambda i: desired[i])
    room, acc = [], 0.0
    for k, i in enumerate(order):
        if k:
            acc += (widths[order[k - 1]] + widths[i]) / 2.0 + gap
        room.append(acc)
    blocks = []                                        # [mean target, count]
    for k, i in enumerate(order):
        blocks.append([desired[i] - room[k], 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            m2, n2 = blocks.pop()
            m1, n1 = blocks.pop()
            blocks.append([(m1 * n1 + m2 * n2) / (n1 + n2), n1 + n2])
    out, k = [0.0] * len(desired), 0
    for mean, count in blocks:
        for _ in range(count):
            out[order[k]] = mean + room[k]
            k += 1
    return out


def side_of(anchor, box):
    """
    The member edge a bar's mark goes beyond: the nearest one; beside the member for a bar standing out above or
    below it (a base's starters: over them is the column cut, user 2026-10-17).
    """
    if anchor[1] > box[3] or anchor[1] < box[1]:
        return 'left' if anchor[0] < (box[0] + box[2]) / 2.0 else 'right'
    d ={'bottom': anchor[1] - box[1], 'top': box[3] - anchor[1], 'left': anchor[0] - box[0], 'right': box[2] - anchor[0]}
    return min(d, key=d.get)


def footprint(item):
    """(width, height) in the view of a mark's text: 'length' along it, 'height' across, turned when 'vertical'."""
    if item.get('vertical'):
        return item['height'], item['length']
    return item['length'], item['height']


def crowded(positions, size, gap):
    """True when marks of `size` along a row, wanted at `positions`, cannot sit side by side over their bars."""
    p = sorted(positions)
    return any(b - a < size + gap for a, b in zip(p, p[1:]))


MAX_TIERS = 3


def tiers(desired, widths, gap, most=MAX_TIERS):
    """
    Row of each mark (0 nearest the member), in order along the row: the nearest row where it stands clear of
    the last mark already there; where no row has room, the one whose last mark is furthest back. So marks of
    bars at close centres split over two or three rows only where they are close.
    """
    order = sorted(range(len(desired)), key=lambda i: desired[i])
    out = [0] * len(desired)
    last = [None] * most                         # (position, width) of the last mark in each row
    for i in order:
        pick = None
        for t in range(most):
            if last[t] is None or desired[i] - last[t][0] >= (widths[i] + last[t][1]) / 2.0 + gap:
                pick = t
                break
        if pick is None:
            pick = min(range(most), key=lambda t: last[t][0] + last[t][1] / 2.0)
        out[i] = pick
        last[pick] = (desired[i], widths[i])
    return out


def _clear_blocks(pos, tier, widths, blocks, gap):
    """Marks standing on a line of `blocks` moved just off it, to the side with room in their row, or a row out."""
    if not blocks:
        return

    def free_at(i, p, t):
        for j in range(len(pos)):
            if j != i and tier[j] == t and abs(pos[j] - p) < (widths[i] + widths[j]) / 2.0 + gap:
                return False
        return not any(abs(b - p) < widths[i] / 2.0 + gap / 2.0 for b in blocks)

    for i in range(len(pos)):
        hit = [b for b in blocks if abs(b - pos[i]) < widths[i] / 2.0 + gap / 4.0]
        if not hit:
            continue
        b = hit[0]
        tries = sorted([b - gap / 2.0 - widths[i] / 2.0, b + gap / 2.0 + widths[i] / 2.0],
                       key=lambda p: abs(p - pos[i]))
        for p in tries:
            if free_at(i, p, tier[i]):
                pos[i] = p
                break
        else:
            for t in range(tier[i] + 1, MAX_TIERS):
                for p in [pos[i]] + tries:
                    if free_at(i, p, t):
                        pos[i], tier[i] = p, t
                        break
                else:
                    continue
                break


def place_pointers(items, box, gap, outside_gap, edges=None, free_gap=None, blocks=None):
    """
    Marks of bars in a section or elevation: items [{'id', 'anchor' (x, y) on the bar, 'length', 'height',
    'vertical' (optional: the text turned to run up the sheet), 'side' (optional: 'top' | 'bottom' | 'left' |
    'right'), 'outside' (optional: its own distance from the member), 'free' (optional: no pointer, so it stands
    over its bar)}]. Each goes in a row beyond its side of the member, packed along it, its near end a fixed
    distance from the member so the texts of a row line up (SMDSC 4th ed. 6.2.2). Free marks of bars too close for them
    side by side split into up to MAX_TIERS rows (tiers); marks with pointers go in a row beyond them.
    edges: {side: coordinate} where a row starts instead of the box's edge; free_gap: between free marks (they
    need less room than texts with pointers). blocks: {side: [coordinates along the row]} of lines no mark may
    stand on (the grid lines a section shows, 2026-10-18 audit). Returns {id: {'centre', 'side', 'box'}}.
    """
    rows = {}
    for it in items:
        rows.setdefault(it.get('side') or side_of(it['anchor'], box), []).append(it)
    start = {'top': box[3], 'bottom': box[1], 'right': box[2], 'left': box[0]}
    start.update(edges or {})
    out = {}
    for side, row in rows.items():
        horizontal = side in ('top', 'bottom')
        desired = [it['anchor'][0] if horizontal else it['anchor'][1] for it in row]
        sizes = [footprint(it) for it in row]
        widths = [w if horizontal else h for w, h in sizes]
        across = [h if horizontal else w for w, h in sizes]
        free = [i for i, it in enumerate(row) if it.get('free')]
        tier = [0] * len(row)
        fgap = gap if free_gap is None else free_gap
        for i, t in zip(free, tiers([desired[i] for i in free], [widths[i] for i in free], fgap)):
            tier[i] = t
        outer = max([tier[i] for i in free]) + 1 if free else 0
        for i, it in enumerate(row):
            if not it.get('free'):
                tier[i] = outer
        pos = [0.0] * len(row)
        for t in set(tier):
            ids = [i for i in range(len(row)) if tier[i] == t]
            g = fgap if t < outer else gap
            for i, p in zip(ids, pack([desired[i] for i in ids], [widths[i] for i in ids], g)):
                pos[i] = p
        _clear_blocks(pos, tier, widths, (blocks or {}).get(side, ()), fgap)
        deep = (max(across[i] for i in free) + gap) if free else 0.0
        base = min(row[i].get('outside', outside_gap) for i in free) if free else None
        sign = 1.0 if side in ('top', 'right') else -1.0
        for i, it in enumerate(row):
            w, h = sizes[i]
            if free:
                level = start[side] + sign * (base + tier[i] * deep + across[i] / 2.0)
                if not it.get('free'):
                    level = start[side] + sign * (max(base + outer * deep, it.get('outside', outside_gap)) +
                                                  across[i] / 2.0)
            else:
                level = start[side] + sign * (it.get('outside', outside_gap) + across[i] / 2.0)
            c = (pos[i], level) if horizontal else (level, pos[i])
            out[it['id']] = {'centre': c, 'side': side,
                             'box': (c[0] - w / 2.0, c[1] - h / 2.0, c[0] + w / 2.0, c[1] + h / 2.0)}
    return out
