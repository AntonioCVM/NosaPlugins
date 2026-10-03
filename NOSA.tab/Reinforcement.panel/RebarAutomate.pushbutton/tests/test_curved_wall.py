# -*- coding: utf-8 -*-
"""T7.9 — plan geometry of curved walls: radial bar angles, arcs cut to stock length with laps."""
from __future__ import division
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))

import curved_wall as cw


def test_bar_angles_keep_the_spacing_along_the_arc():
    angles = cw.bar_angles(0.0, math.pi / 2.0, 5000.0, 200.0, 50.0)
    steps = [(b - a) * 5000.0 for a, b in zip(angles[:-1], angles[1:])]
    assert all(abs(s - 200.0) < 1e-6 for s in steps)
    assert angles[0] * 5000.0 >= 50.0 - 1e-6
    assert (math.pi / 2.0 - angles[-1]) * 5000.0 >= 50.0 - 1e-6


def test_bar_angles_follow_a_clockwise_sweep():
    angles = cw.bar_angles(1.0, -0.5, 4000.0, 250.0, 50.0)
    assert all(b < a for a, b in zip(angles[:-1], angles[1:]))
    assert 0.5 < angles[-1] < angles[0] < 1.0


def test_split_arc_laps_and_stock_lengths():
    r = 6000.0
    pieces = cw.split_arc(0.0, math.pi, r, 12000.0, 600.0)
    lengths = [cw.arc_length_mm(r, a, b) for a, b in pieces]
    assert all(l <= 12000.0 + 1e-6 for l in lengths)
    for (a0, a1), (b0, b1) in zip(pieces[:-1], pieces[1:]):
        assert abs((a1 - b0) * r - 600.0) < 1e-6
    assert abs(pieces[-1][1] - math.pi) < 1e-12


def test_split_arc_staggered_first_piece():
    r = 6000.0
    pieces = cw.split_arc(0.0, math.pi, r, 12000.0, 600.0, first_mm=11200.0)
    assert abs(cw.arc_length_mm(r, *pieces[0]) - 11200.0) < 1e-6


def test_short_arc_is_not_split():
    assert cw.split_arc(0.2, 0.4, 5000.0, 12000.0, 600.0) == [(0.2, 0.4)]


def test_split_arc_clockwise():
    pieces = cw.split_arc(2.0, -1.0, 6000.0, 12000.0, 600.0)
    assert pieces[0][0] == 2.0 and abs(pieces[-1][1] + 1.0) < 1e-12
    assert all(b < a for a, b in pieces)
