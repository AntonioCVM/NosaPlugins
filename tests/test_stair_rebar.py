# -*- coding: utf-8 -*-
"""stair_rebar — flight bars (T7.8): no straight end under P = 5d past a bend (building test 2026-10-25)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NOSA.tab', 'Reinforcement.panel',
                                'RebarAutomate.pushbutton', 'lib'))
import stair_rebar as sr  # noqa: E402

COVER, DIA, ANCHOR = 40.0, 12.0, 425.0


def _run(upper_far, lower_far, u_dia=None):
    slope = 175.0 / 280.0
    length = 2400.0
    top = slope * length
    upper = {'kind': 'landing', 'top': top, 'bottom': top - 200.0, 's_far': upper_far}
    lower = {'kind': 'landing', 'top': 0.0, 'bottom': -200.0, 's_far': lower_far}
    if u_dia:
        upper['u_dia'] = lower['u_dia'] = u_dia
    return {'slope': slope, 'length': length, 'soffit_z0': -200.0 / math.cos(math.atan(slope)), 'pitch_z0': 0.0,
            'lower': lower, 'upper': upper}


def _ends(pts):
    out = []
    if len(pts) > 2:
        out += [math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]),
                math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])]
    return out


def test_no_short_end_past_a_bend_for_any_landing_depth():
    for u_dia in (None, 12.0):
        for far in range(2400, 3400, 2):
            for lower_far in range(-1200, -20, 37):
                run = _run(float(far), float(lower_far), u_dia)
                for fn in (sr.bottom_bar, sr.top_bar):
                    pts = fn(run, COVER, DIA, ANCHOR)
                    assert all(e >= 5.0 * DIA - 1e-6 for e in _ends(pts)), (fn.__name__, far, lower_far, u_dia, pts)


def test_bars_never_turn_back_along_the_flight():
    for far in range(2400, 3400, 2):
        for lower_far in range(-1200, -20, 37):
            run = _run(float(far), float(lower_far))
            for fn in (sr.bottom_bar, sr.top_bar):
                pts = fn(run, COVER, DIA, ANCHOR)
                assert all(b[0] >= a[0] - 1e-6 for a, b in zip(pts, pts[1:])), (fn.__name__, far, lower_far, pts)


def test_short_ends_are_dropped_not_bent():
    pts = sr._no_short_ends([(0.0, 0.0), (34.0, 0.0), (500.0, 300.0), (900.0, 300.0)], 12.0)
    assert pts == [(34.0, 0.0), (500.0, 300.0), (900.0, 300.0)]
    assert sr._no_short_ends([(0.0, 0.0), (30.0, 0.0)], 12.0) == [(0.0, 0.0), (30.0, 0.0)]   # straight bar kept
