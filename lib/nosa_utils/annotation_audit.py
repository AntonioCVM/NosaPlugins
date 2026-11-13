# -*- coding: utf-8 -*-
"""
Audit of a reinforcement drawing's annotations, the geometry only (no Revit): labels overlapping (A3), labels out of
the view's frame (A7), leaders and underlines crossing (A4), labels of one band out of line (A1) and bands set off
their member at different distances (A6). Everything in paper mm, in the view's own axes.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

TOUCH_MM = 0.05


def area_overlap(a, b, tol=0.0):
    """Two boxes (x0, y0, x1, y1) overlapping by more than tol in both directions."""
    return (min(a[2], b[2]) - max(a[0], b[0]) > tol) and (min(a[3], b[3]) - max(a[1], b[1]) > tol)


def shrink(box, by):
    return (box[0] + by, box[1] + by, box[2] - by, box[3] - by)


def _orient(a, b, c):
    v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)


def _near(p, q, tol=TOUCH_MM):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def centred_box(head, box):
    """The part of box centred on head: each way, the shorter of the two halves (a box stretched to one side)."""
    hx = min(head[0] - box[0], box[2] - head[0])
    hy = min(head[1] - box[1], box[3] - head[1])
    if hx <= 0 or hy <= 0:
        return box
    return (head[0] - hx, head[1] - hy, head[0] + hx, head[1] + hy)


def cross(s, t):
    """Two segments crossing properly: through each other, not only touching at an end or running together."""
    a, b = s
    c, d = t
    if _near(a, c) or _near(a, d) or _near(b, c) or _near(b, d):
        return False
    o1, o2, o3, o4 = _orient(a, b, c), _orient(a, b, d), _orient(c, d, a), _orient(c, d, b)
    return o1 * o2 < 0 and o3 * o4 < 0


def segment_hits_box(s, box):
    """A segment passing through a box's inside (Liang-Barsky clip)."""
    (x0, y0), (x1, y1) = s
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


def underlines(seg, box, share=0.35):
    """A level line through the lowest part of a text's box: the line the text is written on, not one crossing it."""
    (x0, y0), (x1, y1) = seg
    if abs(y1 - y0) > TOUCH_MM:
        return False
    return box[1] - TOUCH_MM <= y0 <= box[1] + share * (box[3] - box[1])


def outside(box, frame, tol=0.0):
    """A box not wholly inside the frame."""
    return box[0] < frame[0] - tol or box[1] < frame[1] - tol or box[2] > frame[2] + tol or box[3] > frame[3] + tol


def side_of(box, member):
    """Where a label stands off its member: 'left', 'right', 'above', 'below' or None (over it)."""
    gaps = [('left', member[0] - box[2]), ('right', box[0] - member[2]),
            ('below', member[1] - box[3]), ('above', box[1] - member[3])]
    side, gap = max(gaps, key=lambda g: g[1])
    return side if gap > -TOUCH_MM else None


def near_edge(box, side):
    """The edge of a label towards its member: the line its band shares."""
    return {'left': box[2], 'right': box[0], 'below': box[3], 'above': box[1]}[side]


def bands(labels, member, tol=3.0):
    """
    Labels outside the member grouped in bands: same side, near edges within tol of one another.
    labels {key: box}. Returns [{'side', 'keys', 'edge' (mean), 'spread' (max - min of the near edges), 'off'
    (distance of the band from the member)}].
    """
    by_side = {}
    for key, box in labels.items():
        side = side_of(box, member)
        if side is not None:
            by_side.setdefault(side, []).append((near_edge(box, side), key))
    out = []
    for side, edges in by_side.items():
        edges.sort()
        group = [edges[0]]
        for e in edges[1:]:
            if e[0] - group[-1][0] <= tol:
                group.append(e)
            else:
                out.append(_band(side, group, member))
                group = [e]
        out.append(_band(side, group, member))
    return out


def _band(side, group, member):
    values = [e for e, _k in group]
    edge = sum(values) / len(values)
    off = {'left': member[0] - edge, 'right': edge - member[2], 'below': member[1] - edge,
           'above': edge - member[3]}[side]
    return {'side': side, 'keys': [k for _e, k in group], 'edge': edge, 'spread': max(values) - min(values),
            'off': off}


def overlapping_pairs(boxes, tol=0.0, same=None):
    """[(key_a, key_b)] of boxes overlapping; same(key_a, key_b) True skips a pair that belongs together."""
    keys = sorted(boxes)
    out = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if same is not None and same(a, b):
                continue
            if area_overlap(boxes[a], boxes[b], tol):
                out.append((a, b))
    return out


def crossing_pairs(segments, same=None):
    """[(key_a, key_b)] of segments {key: ((x, y), (x, y))} crossing one another."""
    keys = sorted(segments)
    out = []
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if same is not None and same(a, b):
                continue
            if cross(segments[a], segments[b]):
                out.append((a, b))
    return out


def callout_lines(lines, labels, below_mm=2.0):
    """
    The lines of the calling-ups: each one under a label (its underline) and every line joined end to end with
    one (the jogs and risers back to the zone or bar). lines {key: segment}, labels [box]. Returns a set of keys.
    """
    seeds = set()
    for key, (p, q) in lines.items():
        if abs(p[1] - q[1]) > TOUCH_MM:
            continue
        y, lo, hi = p[1], min(p[0], q[0]), max(p[0], q[0])
        for b in labels:
            if b[1] - below_mm <= y <= b[1] + TOUCH_MM and lo < b[2] and hi > b[0]:
                seeds.add(key)
                break
    found, todo = set(seeds), list(seeds)
    while todo:
        k = todo.pop()
        ends = lines[k]
        for other, seg in lines.items():
            if other in found:
                continue
            if any(_near(e, f) for e in ends for f in seg):
                found.add(other)
                todo.append(other)
    return found
