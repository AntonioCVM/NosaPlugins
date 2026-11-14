# -*- coding: utf-8 -*-
"""Revit-free helpers of Element Join: spatial pairing and the join decision."""
import math

_CELL_FT = 10.0
_MAX_CELLS = 3000


def _cells(box, tol, cell):
    x0, y0, z0, x1, y1, z1 = box
    lo = [int(math.floor((v - tol) / cell)) for v in (x0, y0, z0)]
    hi = [int(math.floor((v + tol) / cell)) for v in (x1, y1, z1)]
    return lo, hi


def boxes_touch(a, b, tol):
    for k in range(3):
        if a[k] - tol > b[k + 3] or b[k] - tol > a[k + 3]:
            return False
    return True


def candidate_pairs(boxes, tol_ft, cell_ft=_CELL_FT):
    """Index pairs (i < j) whose boxes, grown by the tolerance, overlap. A box is None when unknown."""
    grid, big, pairs = {}, [], set()
    for i, box in enumerate(boxes):
        if box is None:
            continue
        lo, hi = _cells(box, tol_ft, cell_ft)
        count = 1
        for k in range(3):
            count *= hi[k] - lo[k] + 1
        if count > _MAX_CELLS:
            big.append(i)
            continue
        for cx in range(lo[0], hi[0] + 1):
            for cy in range(lo[1], hi[1] + 1):
                for cz in range(lo[2], hi[2] + 1):
                    grid.setdefault((cx, cy, cz), []).append(i)
    for members in grid.values():
        for p in range(len(members)):
            for q in range(p + 1, len(members)):
                i, j = members[p], members[q]
                if boxes_touch(boxes[i], boxes[j], tol_ft):
                    pairs.add((min(i, j), max(i, j)))
    for i in big:
        for j, other in enumerate(boxes):
            if j != i and other is not None and boxes_touch(boxes[i], other, tol_ft):
                pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def decide(rank_a, rank_b, joined, a_cuts_b, has_overlap, fix_existing=True,
           require_overlap=True, forced=None):
    """(action, dominant, message): action is join / fix / ok / skip, dominant is 'a', 'b' or None."""
    if forced in ('a', 'b'):
        dominant = forced
    elif rank_a is None and rank_b is None:
        return u'skip', None, u'Neither category is in the priority list'
    else:
        ra = 999 if rank_a is None else rank_a
        rb = 999 if rank_b is None else rank_b
        dominant = u'a' if ra < rb else u'b' if rb < ra else None
    if joined:
        if dominant is None or not fix_existing:
            return u'ok', dominant, u'Already joined'
        correct = a_cuts_b if dominant == u'a' else not a_cuts_b
        if correct:
            return u'ok', dominant, u'Already joined, the order is correct'
        return u'fix', dominant, u'Joined with the wrong cutting order'
    if require_overlap and has_overlap is False:
        return u'skip', None, u'No overlap: the elements only touch or are close'
    return u'join', dominant, u'Not joined yet'
