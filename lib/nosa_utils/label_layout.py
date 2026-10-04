# -*- coding: utf-8 -*-
"""Move annotation rectangles (view-plane units) apart so none overlaps another or an obstacle."""


def _overlaps(a, b, gap):
    return (a[0] < b[2] + gap and b[0] < a[2] + gap and
            a[1] < b[3] + gap and b[1] < a[3] + gap)


def _shift(rect, dx, dy):
    return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)


def candidate_offsets(width, height, gap, rings=8):
    """Offsets nearest first: up/down by one tag height + gap, then sideways, ring by ring."""
    step_y = height + gap
    step_x = width + gap
    out = [(0.0, 0.0)]
    for k in range(1, rings + 1):
        ring = [(0.0, k * step_y), (0.0, -k * step_y), (k * step_x, 0.0), (-k * step_x, 0.0),
                (k * step_x, k * step_y), (-k * step_x, k * step_y),
                (k * step_x, -k * step_y), (-k * step_x, -k * step_y)]
        out.extend(sorted(ring, key=lambda d: (abs(d[0]) / max(step_x, 1e-9) + abs(d[1]) / max(step_y, 1e-9),
                                               abs(d[0]))))
    return out


def deoverlap(rects, obstacles=(), gap=0.0, rings=8):
    """
    rects: [(xmin, ymin, xmax, ymax)] in placement order; obstacles: fixed rectangles.
    Returns [(dx, dy)] per rect — (0, 0) when it already fits; the nearest free candidate
    otherwise; the least-overlapping candidate if none is free within `rings`.
    """
    placed = list(obstacles)
    moves = []
    for rect in rects:
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        best, best_hits = None, None
        for dx, dy in candidate_offsets(w, h, gap, rings):
            moved = _shift(rect, dx, dy)
            hits = sum(1 for other in placed if _overlaps(moved, other, gap))
            if hits == 0:
                best, best_hits = (dx, dy), 0
                break
            if best_hits is None or hits < best_hits:
                best, best_hits = (dx, dy), hits
        moves.append(best)
        placed.append(_shift(rect, best[0], best[1]))
    return moves


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(p1, p2, q1, q2):
    """True when segments p1-p2 and q1-q2 properly intersect (touching ends do not count)."""
    d1, d2 = _cross(q1, q2, p1), _cross(q1, q2, p2)
    d3, d4 = _cross(p1, p2, q1), _cross(p1, p2, q2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and 0 not in (d1, d2, d3, d4)


def _centre(rect):
    return ((rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0)


def _at(rect, centre):
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    return (centre[0] - w / 2.0, centre[1] - h / 2.0, centre[0] + w / 2.0, centre[1] + h / 2.0)


def layout_tags(anchors, rects, obstacles=(), gap=0.0, leader_after=1.5, rings=8, max_swaps=50):
    """
    anchors: [(x, y)] the point each tag annotates; rects: [(xmin, ymin, xmax, ymax)] each tag at
    its natural spot (or where it already is). Tags move to the nearest free spot (deoverlap); a tag
    whose anchor lies further than leader_after tag heights from it gets a leader. Then crossing
    leaders are undone by swapping the two tags' places when that creates no overlap.
    Returns [(dx, dy, leader)] per tag.
    """
    moves = deoverlap(rects, obstacles, gap, rings)
    placed = [_shift(r, dx, dy) for r, (dx, dy) in zip(rects, moves)]
    def needs_leader(anchor, rect):
        reach = leader_after * max(rect[3] - rect[1], 1e-9)
        return not (rect[0] - reach <= anchor[0] <= rect[2] + reach and
                    rect[1] - reach <= anchor[1] <= rect[3] + reach)

    leaders = [needs_leader(a, p) for a, p in zip(anchors, placed)]

    def crossing_pair():
        idx = [i for i, lead in enumerate(leaders) if lead]
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if segments_cross(anchors[i], _centre(placed[i]), anchors[j], _centre(placed[j])):
                    yield i, j

    def crosses_any(k, rect):
        head = _centre(rect)
        for m in range(len(placed)):
            if m != k and leaders[m] and segments_cross(anchors[k], head, anchors[m], _centre(placed[m])):
                return True
        return False

    def relocate(k, reach=rings):
        """Another free spot for tag k, near its natural place, whose leader crosses no other."""
        others = [p for m, p in enumerate(placed) if m != k] + list(obstacles)
        w, h = rects[k][2] - rects[k][0], rects[k][3] - rects[k][1]
        for dx, dy in candidate_offsets(w, h, gap, reach):
            rect = _shift(rects[k], dx, dy)
            if any(_overlaps(rect, o, gap) for o in others):
                continue
            if needs_leader(anchors[k], rect) and crosses_any(k, rect):
                continue
            return rect
        return None

    swaps = 0
    changed = True
    while changed and swaps < max_swaps:
        changed = False
        for i, j in crossing_pair():
            ri, rj = _at(placed[i], _centre(placed[j])), _at(placed[j], _centre(placed[i]))
            others = [p for k, p in enumerate(placed) if k not in (i, j)] + list(obstacles)
            blocked = (any(_overlaps(ri, o, gap) for o in others) or
                       any(_overlaps(rj, o, gap) for o in others) or _overlaps(ri, rj, gap))
            if not blocked:
                placed[i], placed[j] = ri, rj
                leaders[i], leaders[j] = needs_leader(anchors[i], ri), needs_leader(anchors[j], rj)
            else:
                moved = None
                for k in (j, i):
                    rect = relocate(k)
                    if rect is not None:
                        placed[k] = rect
                        leaders[k] = needs_leader(anchors[k], rect)
                        moved = k
                        break
                if moved is None:
                    continue
            swaps += 1
            changed = True
            break
    # last resort for a pair still crossing: look further out for one of the two
    for i, j in list(crossing_pair()):
        if not segments_cross(anchors[i], _centre(placed[i]), anchors[j], _centre(placed[j])):
            continue
        for k in (j, i):
            rect = relocate(k, 3 * rings)
            if rect is not None:
                placed[k] = rect
                leaders[k] = needs_leader(anchors[k], rect)
                break
    out = []
    for r, p, lead in zip(rects, placed, leaders):
        out.append((p[0] - r[0], p[1] - r[1], lead))
    return out
