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
    Tries the extension past each end, outside the member first (nearest edge first), pushing out past texts
    already placed; then next to an end inside the member. Returns {'centre', 'end' ('a'|'b'), 'outside', 'box'}
    and appends the box to `placed`.
    """
    a, b = item['a'], item['b']
    run = (b[0] - a[0], b[1] - a[1])
    n = (run[0] ** 2 + run[1] ** 2) ** 0.5 or 1.0
    u = (run[0] / n, run[1] / n)
    ends = [('b', b, u), ('a', a, (-u[0], -u[1]))]
    ends.sort(key=lambda e: exit_distance(e[1], e[2], box))
    for inside in (False, True):
        for name, p, out in ends:
            start = gap if inside else exit_distance(p, out, box) + outside_gap
            for _ in range(tries):
                c = (p[0] + out[0] * (start + item['length'] / 2.0), p[1] + out[1] * (start + item['length'] / 2.0))
                bx = text_box(c, out, item['length'], item['height'])
                hits = [q for q in placed if overlap(bx, q, gap)]
                if not hits:
                    placed.append(bx)
                    return {'centre': c, 'end': name, 'outside': not inside, 'box': bx}
                if inside:
                    break
                far = max(abs((q[2] if out[0] > 0 else q[0]) - p[0]) * abs(out[0]) +
                          abs((q[3] if out[1] > 0 else q[1]) - p[1]) * abs(out[1]) for q in hits)
                start = far + gap
    c = (b[0] + u[0] * (gap + item['length'] / 2.0), b[1] + u[1] * (gap + item['length'] / 2.0))
    bx = text_box(c, u, item['length'], item['height'])
    placed.append(bx)
    return {'centre': c, 'end': 'b', 'outside': False, 'box': bx}


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


def place_pointers(items, box, gap, outside_gap):
    """
    Marks of bars in a section or elevation: items [{'id', 'anchor' (x, y) on the bar, 'length', 'height',
    'side' (optional: 'top' | 'bottom' | 'left' | 'right')}]. Each goes in a row beyond its side of the member,
    packed along it. Returns {id: {'centre', 'side'}}.
    """
    rows = {}
    for it in items:
        rows.setdefault(it.get('side') or side_of(it['anchor'], box), []).append(it)
    out = {}
    for side, row in rows.items():
        horizontal = side in ('top', 'bottom')
        desired = [it['anchor'][0] if horizontal else it['anchor'][1] for it in row]
        widths = [it['length'] if horizontal else it['height'] for it in row]
        across = max((it['height'] if horizontal else it['length']) for it in row)
        pos = pack(desired, widths, gap)
        level = {'top': box[3] + outside_gap + across / 2.0, 'bottom': box[1] - outside_gap - across / 2.0,
                 'right': box[2] + outside_gap + across / 2.0, 'left': box[0] - outside_gap - across / 2.0}[side]
        for it, p in zip(row, pos):
            out[it['id']] = {'centre': (p, level) if horizontal else (level, p), 'side': side}
    return out
