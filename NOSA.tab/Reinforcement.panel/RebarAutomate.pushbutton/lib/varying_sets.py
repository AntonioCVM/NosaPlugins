# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Revit "varying rebar sets" for bars cut by an inclined or curved face
(user decision 2026-10-05). Pure geometry, mm, no Revit: bars are point chains [(x, y, z), ...].

Rows of bars whose ends meet a chamfer each have their own length. One shape-driven set with
DistributionType = VaryingLength holds them all: every bar keeps the shape of the first one and
its ends follow the host faces they are constrained to. Revit numbers the set as one bar mark
and its bars with a suffix (ReinforcementSettings.NumberVaryingLengthRebarsIndividually = False),
and a BBS sorted by Rebar Number Suffix lists each bar with its real dimensions.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

_TOL = 1e-6


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    return math.sqrt(_dot(a, a))


def _unit(a):
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > _TOL else (0.0, 0.0, 0.0)


def _scale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def directions(points):
    """Unit direction of every segment of a chain."""
    return [_unit(_sub(q, p)) for p, q in zip(points[:-1], points[1:])]


def plane_normal(points, step=None):
    """
    Unit normal of the plane a bar lies in: from two of its segments that are not parallel; a
    straight bar takes the part of `step` (the offset to the next bar) square to the bar.
    """
    dirs = directions(points)
    for i in range(len(dirs)):
        for j in range(i + 1, len(dirs)):
            n = _cross(dirs[i], dirs[j])
            if _norm(n) > 1e-3:
                return _unit(n)
    if step is None or not dirs:
        return None
    d = dirs[0]
    perp = _sub(step, _scale(d, _dot(step, d)))
    return _unit(perp) if _norm(perp) > _TOL else None


def same_shape_family(a, b, angle_tol=1e-3):
    """Two chains a varying set can hold together: as many segments, each one parallel."""
    if len(a) != len(b) or len(a) < 2:
        return False
    return all(_dot(u, v) > 1.0 - angle_tol for u, v in zip(directions(a), directions(b)))


def _offset(a, b, normal):
    """Distance from bar a's plane to bar b's, along normal."""
    return _dot(_sub(b[0], a[0]), normal)


def split_runs(chains, spacing_tol_mm=1.0, min_bars=2):
    """
    Consecutive chains that one varying set can represent: same segment family, all in parallel
    planes (square to one normal) at one constant step. Returns [[index, ...], ...] in order;
    chains no run can take come back as runs of one.
    """
    runs = []
    current = []
    normal = None
    step = None
    for i, chain in enumerate(chains):
        if not current:
            current, normal, step = [i], None, None
            continue
        prev = chains[current[-1]]
        ok = same_shape_family(chains[current[0]], chain)
        if ok:
            n = normal
            if n is None:
                n = plane_normal(chains[current[0]], _sub(chain[0], prev[0]))
                if n is not None and _offset(prev, chain, n) < 0:
                    n = _scale(n, -1.0)       # towards the next bar
            if n is None:
                ok = False
            else:
                d = _offset(prev, chain, n)
                # the bars must sit in parallel planes: no drift inside the plane is allowed
                # beyond what the face constraints give (checked on the whole chain later)
                ok = d > spacing_tol_mm and (step is None or abs(d - step) <= spacing_tol_mm)
                if ok and normal is None:
                    normal = n
                if ok and step is None:
                    step = d
        if ok:
            current.append(i)
        else:
            runs.append(current)
            current, normal, step = [i], None, None
    if current:
        runs.append(current)
    out = []
    for run in runs:
        if len(run) >= min_bars:
            out.append(run)
        else:
            out.extend([[i] for i in run])
    return out


def set_layout(chains):
    """(normal, array length mm, count) of the varying set holding these chains, first to last."""
    first, last = chains[0], chains[-1]
    normal = plane_normal(first, _sub(last[0], first[0]))
    if normal is None:
        return None
    length = _dot(_sub(last[0], first[0]), normal)
    if length < 0:
        normal, length = _scale(normal, -1.0), -length
    return normal, length, len(chains)


def end_error_mm(actual, expected):
    """How far a built bar's two ends are from the wanted ones (either direction of the chain)."""
    a0, a1 = actual[0], actual[-1]
    e0, e1 = expected[0], expected[-1]
    straight = _norm(_sub(a0, e0)) + _norm(_sub(a1, e1))
    reversed_ = _norm(_sub(a0, e1)) + _norm(_sub(a1, e0))
    return min(straight, reversed_)
