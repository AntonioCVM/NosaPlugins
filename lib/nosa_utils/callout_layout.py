# -*- coding: utf-8 -*-
"""
Where the calling-up of bars goes on a reinforcement drawing (IStructE SMDSC 3.3, 6.2.2), no Revit: on the
extension of a zone's indicator line, outside the member, else inside next to the zone; and the bar marks of
sections and elevations in rows outside the member, each over its bar, packed so no two touch and the
pointers stay as short and straight as they can. View coordinates in model mm; boxes (x0, y0, x1, y1).
"""


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
    Calling-up of one zone (SMDSC 6.2.2): item {'a', 'b' (ends of the indicator line), 'length', 'height' (text)}.
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
    """The member edge a bar's mark goes beyond: the nearest one."""
    d = {'bottom': anchor[1] - box[1], 'top': box[3] - anchor[1], 'left': anchor[0] - box[0], 'right': box[2] - anchor[0]}
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
    Row of each mark (0 nearest the member): marks whose bars are too close for them side by side form runs, and
    within a run mark k takes row k mod n, n the fewest rows (up to `most`) that give each its room; a mark with
    room of its own stays in row 0.
    """
    order = sorted(range(len(desired)), key=lambda i: desired[i])
    out = [0] * len(desired)
    run = []

    def close(run):
        if len(run) < 2:
            return
        need = max(widths[i] for i in run) + gap
        pitch = min(desired[b] - desired[a] for a, b in zip(run, run[1:])) or 1e-6
        n = min(most, max(1, int(-(-need // pitch))))
        for k, i in enumerate(run):
            out[i] = k % n
    for i in order:
        if run and desired[i] - desired[run[-1]] >= (widths[i] + widths[run[-1]]) / 2.0 + gap:
            close(run)
            run = []
        run.append(i)
    close(run)
    return out


def place_pointers(items, box, gap, outside_gap, edges=None):
    """
    Marks of bars in a section or elevation: items [{'id', 'anchor' (x, y) on the bar, 'length', 'height',
    'vertical' (optional: the text turned to run up the sheet), 'side' (optional: 'top' | 'bottom' | 'left' |
    'right'), 'outside' (optional: its own distance from the member), 'free' (optional: no pointer, so it stands
    over its bar)}]. Each goes in a row beyond its side of the member, packed along it, its near end a fixed
    distance from the member so the texts of a row line up (SMDSC 6.2.2). Free marks of bars too close for them
    side by side split into up to MAX_TIERS rows (tiers); marks with pointers go in a row beyond them.
    edges: {side: coordinate} where a row starts instead of the box's edge. Returns {id: {'centre', 'side', 'box'}}.
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
        for i, t in zip(free, tiers([desired[i] for i in free], [widths[i] for i in free], gap)):
            tier[i] = t
        outer = max([tier[i] for i in free]) + 1 if free else 0
        for i, it in enumerate(row):
            if not it.get('free'):
                tier[i] = outer
        pos = [0.0] * len(row)
        for t in set(tier):
            ids = [i for i in range(len(row)) if tier[i] == t]
            for i, p in zip(ids, pack([desired[i] for i in ids], [widths[i] for i in ids], gap)):
                pos[i] = p
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
