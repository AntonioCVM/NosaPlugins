# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — how each end of a wall meets the other selected walls (IStructE SMDSC MW2).

Plan geometry in mm, no Revit. An L corner (two wall ends meeting) has one wall running THROUGH to
the other's outer face and the other STOPPING at its inner face, closed by U-bars looped round the
corner; a T junction has the abutting wall stopping, the other untouched; anything else is FREE
(the wall's own end U-bars). The lower element id runs through, so a corner is decided the same way
whichever wall is processed first.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

FREE, THROUGH, STOP = u'free', u'through', u'stop'
_PARALLEL_SIN = 0.2          # walls within ~12 degrees of each other do not form a corner


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _norm(v):
    return math.hypot(v[0], v[1])


def _point_segment(p, a, b):
    """(distance, t) from p to segment a-b, t in [0, 1] along it."""
    ab = _sub(b, a)
    length2 = ab[0] ** 2 + ab[1] ** 2
    if length2 <= 0.0:
        return _norm(_sub(p, a)), 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / length2))
    q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
    return _norm(_sub(p, q)), t


def _sin_between(a0, a1, b0, b1):
    u, v = _sub(a1, a0), _sub(b1, b0)
    nu, nv = _norm(u), _norm(v)
    if nu <= 0.0 or nv <= 0.0:
        return 0.0
    return abs(u[0] * v[1] - u[1] * v[0]) / (nu * nv)


def classify(walls, tolerance_mm=5.0):
    """
    walls: [{'id', 'p0': (x, y), 'p1': (x, y), 'thickness_mm'}] (location lines, mm).
    Returns {id: (end0, end1)}, each end {'mode': FREE | THROUGH | STOP, 'other_half_mm',
    'other_id'} (other_half_mm: half the thickness of the wall met, 0 when free).
    """
    out = dict((w['id'], [{'mode': FREE, 'other_half_mm': 0.0, 'other_id': None},
                          {'mode': FREE, 'other_half_mm': 0.0, 'other_id': None}]) for w in walls)
    for a in walls:
        for k, end in enumerate((a['p0'], a['p1'])):
            for b in walls:
                if b['id'] == a['id'] or _sin_between(a['p0'], a['p1'], b['p0'], b['p1']) < _PARALLEL_SIN:
                    continue
                reach = b['thickness_mm'] / 2.0 + tolerance_mm
                dist, t = _point_segment(end, b['p0'], b['p1'])
                if dist > reach:
                    continue
                b_len = _norm(_sub(b['p1'], b['p0']))
                near_b_end = min(t, 1.0 - t) * b_len <= a['thickness_mm'] / 2.0 + tolerance_mm
                if near_b_end:
                    mode = THROUGH if a['id'] < b['id'] else STOP      # L corner
                else:
                    mode = STOP                                        # T junction: a abuts b
                out[a['id']][k] = {'mode': mode, 'other_half_mm': b['thickness_mm'] / 2.0,
                                   'other_id': b['id']}
                break
    return dict((i, tuple(v)) for i, v in out.items())
