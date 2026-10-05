# -*- coding: utf-8 -*-
"""Varying rebar sets for bars cut by a chamfer (pure geometry)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import varying_sets as vs  # noqa: E402


def _u_bar(y, x0, x1, z0=-852.0, z1=-100.0):
    """A bottom U-bar along X at row y, legs up at x0 and x1."""
    return [(x0, y, z1), (x0, y, z0), (x1, y, z0), (x1, y, z1)]


def _chamfer_rows():
    # 3-pile cap: both ends move in 71 mm per 142 mm row (faces at 1:2)
    return [_u_bar(5100.0 + 141.7 * i, 9101.0 + 70.8 * i, 10899.0 - 70.8 * i) for i in range(7)]


def test_plane_normal_of_a_u_bar_is_square_to_its_plane():
    n = vs.plane_normal(_u_bar(0.0, 0.0, 1000.0))
    assert abs(abs(n[1]) - 1.0) < 1e-9 and abs(n[0]) < 1e-9 and abs(n[2]) < 1e-9


def test_plane_normal_of_a_straight_bar_comes_from_the_next_row():
    n = vs.plane_normal([(0.0, 0.0, 0.0), (1000.0, 0.0, 0.0)], step=(70.0, 150.0, 0.0))
    assert abs(n[1] - 1.0) < 1e-9


def test_chamfer_rows_make_one_run():
    assert vs.split_runs(_chamfer_rows()) == [list(range(7))]


def test_rows_of_another_shape_or_step_start_a_new_run():
    rows = _chamfer_rows()[:3] + [[(9300.0, 5600.0, -852.0), (10700.0, 5600.0, -852.0)]] + \
        [_u_bar(6000.0, 9500.0, 10500.0)]
    assert vs.split_runs(rows) == [[0, 1, 2], [3], [4]]


def test_set_layout_spans_first_to_last_row():
    normal, length, count = vs.set_layout(_chamfer_rows())
    assert abs(normal[1] - 1.0) < 1e-9
    assert abs(length - 6 * 141.7) < 1e-6 and count == 7


def test_end_error_ignores_chain_direction():
    a = _u_bar(0.0, 0.0, 1000.0)
    assert vs.end_error_mm(list(reversed(a)), a) < 1e-9
    assert abs(vs.end_error_mm(_u_bar(0.0, 10.0, 1000.0), a) - 10.0) < 1e-9
