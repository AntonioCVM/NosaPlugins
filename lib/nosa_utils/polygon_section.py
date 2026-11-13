# -*- coding: utf-8 -*-
"""
T8.58 (2026-10-25): columns of an L, T or other square-cornered section, no Revit. The section's outline (plan,
mm) is turned into its own frame, its link and bar lines inset by cover, the link line split into overlapping
rectangles (one closed link each - an L gets one link per leg, SMDSC 4th ed. 6.4: every corner bar held by a link
corner) and the bars set at every corner of the section and of the links, with bars between where the gap is
wider than allowed.
"""
import math

TOL = 0.5          # mm


def frame(outline):
    """(cos, sin) of the section's first edge: the frame its sides run square to."""
    (x0, y0), (x1, y1) = outline[0], outline[1]
    a = math.atan2(y1 - y0, x1 - x0)
    return math.cos(a), math.sin(a)


def to_local(points, rot):
    c, s = rot
    return [(x * c + y * s, -x * s + y * c) for x, y in points]


def to_plan(points, rot):
    c, s = rot
    return [(x * c - y * s, x * s + y * c) for x, y in points]


def square_cornered(outline, tol_deg=0.5):
    """Every side of the outline square to the first one (an L, a T, a cross, a rectangle)."""
    local = to_local(outline, frame(outline))
    for (x0, y0), (x1, y1) in zip(local, local[1:] + local[:1]):
        dx, dy = x1 - x0, y1 - y0
        ang = abs(math.degrees(math.atan2(dy, dx))) % 90.0
        if min(ang, 90.0 - ang) > tol_deg:
            return False
    return True


def _area(poly):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1])) / 2.0


def _clean(poly):
    """No repeated or straight-through vertices."""
    out = []
    for p in poly:
        if not out or abs(p[0] - out[-1][0]) > TOL or abs(p[1] - out[-1][1]) > TOL:
            out.append(p)
    if len(out) > 1 and abs(out[0][0] - out[-1][0]) <= TOL and abs(out[0][1] - out[-1][1]) <= TOL:
        out.pop()
    keep = []
    n = len(out)
    for i in range(n):
        a, b, c = out[i - 1], out[i], out[(i + 1) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if abs(cross) > TOL:
            keep.append(b)
    return keep


def inset(poly, d):
    """The square-cornered polygon (local frame) moved in by d all round."""
    poly = _clean(poly)
    if _area(poly) < 0:
        poly = list(reversed(poly))
    n = len(poly)
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        nx, ny = -dy / length, dx / length              # inward for a counter-clockwise outline
        lines.append(((x0 + nx * d, y0 + ny * d), (dx / length, dy / length)))
    out = []
    for i in range(n):
        (p, u), (q, v) = lines[i - 1], lines[i]
        den = u[0] * v[1] - u[1] * v[0]
        t = ((q[0] - p[0]) * v[1] - (q[1] - p[1]) * v[0]) / den
        out.append((p[0] + u[0] * t, p[1] + u[1] * t))
    return out


def _inside(poly, x, y):
    hit = False
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def rectangles(poly):
    """
    The square-cornered polygon (local frame) as overlapping rectangles, each as wide and as tall as it can be
    (an L: one per leg; a T: the flange and the web): [(x0, y0, x1, y1)].
    """
    xs = sorted(set(round(x, 3) for x, _y in poly))
    ys = sorted(set(round(y, 3) for _x, y in poly))
    cols, rows = len(xs) - 1, len(ys) - 1
    cell = [[_inside(poly, (xs[i] + xs[i + 1]) / 2.0, (ys[j] + ys[j + 1]) / 2.0) for j in range(rows)]
            for i in range(cols)]

    def full(i0, i1, j0, j1):
        return all(cell[i][j] for i in range(i0, i1 + 1) for j in range(j0, j1 + 1))
    found = set()
    for i in range(cols):
        for j in range(rows):
            if not cell[i][j]:
                continue
            for wide_first in (True, False):
                i0 = i1 = i
                j0 = j1 = j
                steps = [('i', -1), ('i', 1), ('j', -1), ('j', 1)] if wide_first else \
                    [('j', -1), ('j', 1), ('i', -1), ('i', 1)]
                for axis, step in steps:
                    while True:
                        if axis == 'i':
                            ni0, ni1 = (i0 - 1, i1) if step < 0 else (i0, i1 + 1)
                            if ni0 < 0 or ni1 >= cols or not full(ni0, ni1, j0, j1):
                                break
                            i0, i1 = ni0, ni1
                        else:
                            nj0, nj1 = (j0 - 1, j1) if step < 0 else (j0, j1 + 1)
                            if nj0 < 0 or nj1 >= rows or not full(i0, i1, nj0, nj1):
                                break
                            j0, j1 = nj0, nj1
                found.add((xs[i0], ys[j0], xs[i1 + 1], ys[j1 + 1]))
    rects = sorted(found)
    return [r for r in rects if not any(o != r and o[0] <= r[0] and o[1] <= r[1] and o[2] >= r[2] and o[3] >= r[3]
                                        for o in rects)]


def bar_positions(bar_poly, link_rects, step, max_gap):
    """
    Bars (local frame) at every corner of the bar line and of each link (its rectangle moved in by step, link
    centre line to bar centre), and between them along every side so no gap is wider than max_gap.
    """
    points = list(bar_poly)
    for x0, y0, x1, y1 in link_rects:
        points += [(x0 + step, y0 + step), (x1 - step, y0 + step), (x1 - step, y1 - step), (x0 + step, y1 - step)]
    n = len(bar_poly)
    for i in range(n):
        (x0, y0), (x1, y1) = bar_poly[i], bar_poly[(i + 1) % n]
        length = math.hypot(x1 - x0, y1 - y0)
        k = int(math.ceil(length / max_gap - 1e-9))
        for m in range(1, k):
            points.append((x0 + (x1 - x0) * m / k, y0 + (y1 - y0) * m / k))
    out = []
    for p in points:
        if not any(abs(p[0] - q[0]) <= TOL and abs(p[1] - q[1]) <= TOL for q in out):
            out.append(p)
    return out


def layout(outline, cover_mm, link_dia_mm, bar_dia_mm, max_gap_mm=200.0):
    """
    The section's bars and links in plan (mm): {'bars': [(x, y)], 'links': [[(x, y) x 4]]}, or None when the
    outline is not square-cornered.
    """
    if len(outline) < 4 or not square_cornered(outline):
        return None
    rot = frame(outline)
    local = _clean(to_local(outline, rot))
    link_line = inset(local, cover_mm + link_dia_mm / 2.0)
    bar_line = inset(local, cover_mm + link_dia_mm + bar_dia_mm / 2.0)
    rects = rectangles(link_line)
    bars = bar_positions(bar_line, rects, (link_dia_mm + bar_dia_mm) / 2.0, max_gap_mm)
    links = [to_plan([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], rot) for x0, y0, x1, y1 in rects]
    return {'bars': to_plan(bars, rot), 'links': links}
