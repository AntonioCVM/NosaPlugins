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
