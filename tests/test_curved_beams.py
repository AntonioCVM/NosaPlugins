# -*- coding: utf-8 -*-
"""nosa_utils.curved_beams — beams curved on plan (T8.58)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import curved_beams as cb  # noqa: E402


def _pt(r, a):
    return (r * math.cos(a), r * math.sin(a))


def test_angle_range_of_a_cut_back_clockwise_beam():
    # clockwise arc from 90 to 0 degrees, the solid cut back 0.1 rad at both ends
    pts = [_pt(r, a) for r in (4850.0, 5150.0) for a in (math.pi / 2 - 0.1, 0.1)]
    t0, t1, r0, r1 = cb.angle_range(pts, (0.0, 0.0), math.pi / 2, -math.pi / 2)
    assert abs(t0 - 0.1) < 1e-9 and abs(t1 - (math.pi / 2 - 0.1)) < 1e-9
    assert abs(r0 - 4850.0) < 1e-6 and abs(r1 - 5150.0) < 1e-6
    assert abs(cb.angle_at(math.pi / 2, -math.pi / 2, t0) - (math.pi / 2 - 0.1)) < 1e-9


def test_angle_range_across_the_minus_x_axis():
    pts = [_pt(1000.0, a) for a in (math.pi - 0.2, -math.pi + 0.2)]
    t0, t1, _, _ = cb.angle_range(pts, (0.0, 0.0), math.pi - 0.2, 0.4)
    assert abs(t0) < 1e-9 and abs(t1 - 0.4) < 1e-9


def test_bar_radii():
    assert cb.bar_radii(4850.0, 5150.0, 58.0, 2) == [4908.0, 5092.0]
    assert cb.bar_radii(4850.0, 5150.0, 58.0, 3)[1] == 5000.0
    assert cb.bar_radii(4850.0, 5150.0, 58.0, 1) == [5000.0]


def test_outer_leg_keeps_the_pitch():
    centre = cb.link_pitch_at_centre_mm(200.0, 5000.0, 5100.0)
    assert centre < 200.0 and abs(centre * 5100.0 / 5000.0 - 200.0) < 1e-9


def test_link_angles_are_centred_and_exact():
    ts = cb.link_angles(0.0, 1.0, 5000.0, 200.0, 50.0)
    steps = [(b - a) * 5000.0 for a, b in zip(ts, ts[1:])]
    assert all(abs(s - 200.0) < 1e-6 for s in steps)
    assert abs(ts[0] * 5000.0 - (5000.0 - ts[-1] * 5000.0)) < 1e-6      # same end gaps
    assert ts[0] * 5000.0 >= 50.0
