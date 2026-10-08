# -*- coding: utf-8 -*-
"""IStructE SMDSC MCB1 corbels: bar counts and bar geometry (pure)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import corbels as cb  # noqa: E402

COLUMN = {'depth': 400.0, 'half_along': 200.0, 'cover': 40.0, 'link_dia': 8.0, 'bar_dia': 16.0, 'base': 0.0}
SLOPED = {'top': 2200.0, 'projection': 300.0, 'width': 380.0, 'depth_face': 500.0, 'depth_tip': 250.0, 'cover': 40.0}
BARS = {'main_dia': 16.0, 'main_loops': 2, 'secondary_dia': 10.0, 'compression_dia': 12.0,
        'lap_mm': 800.0, 'anchorage_mm': 500.0}


def test_counts():
    assert cb.compression_bar_count(380.0, 12.0) == 4          # 380 mm2 needed, 113 each
    assert cb.compression_bar_count(150.0, 16.0) == 2          # never fewer than two
    assert cb.secondary_loop_count(2, 16.0, 10.0) == 3         # 0.5 x 2 x 201 = 201 -> 3 x 79
    assert cb.layer_pitch_mm(16.0) == 41.0 and cb.layer_pitch_mm(32.0) == 64.0


def test_reach_follows_the_soffit():
    assert cb.reach_at_mm(2100.0, SLOPED) == 300.0             # above the tip's soffit
    assert cb.reach_at_mm(1700.0, SLOPED) == 0.0               # at the foot on the column face
    assert abs(cb.reach_at_mm(1825.0, SLOPED) - 150.0) < 1e-6  # half way down the slope


def test_main_loops_cross_the_column_and_turn_down_a_lap():
    out = cb.build(SLOPED, COLUMN, BARS)
    assert len(out['main']) == 2
    loop = out['main'][0]
    assert loop[2][0] == 300.0 - 40.0 - 8.0                     # back at the outer face cover
    assert loop[0][0] == -(400.0 - 64.0)                        # legs inside the column's far bars
    assert loop[1][2] - loop[0][2] == 800.0                     # tension lap down
    assert loop[1][1] == min(190.0 - 40.0, 200.0 - 64.0) - 8.0
    assert len(out['secondary']) == 3
    for u in out['secondary']:                                 # every U back inside the sloped soffit
        assert u[1][0] <= cb.reach_at_mm(u[1][2] - 5.0, SLOPED) - 40.0 - 5.0 + 1e-6
    assert len(out['compression']) == 4
    bar = out['compression'][0]
    assert bar[0][0] == bar[1][0] and bar[0][2] > bar[1][2]   # down the outer face first
    assert bar[2][0] < 0.0                                     # then on into the column
    assert out['top_links'] == [2250.0, 2325.0]


def test_rectangular_corbel_and_welded_note():
    rect = dict(SLOPED, depth_tip=500.0)
    out = cb.build(rect, COLUMN, dict(BARS, main_dia=20.0))
    assert any(u'MCB2' in n for n in out['notes'])
    bar = out['compression'][0]
    assert abs(bar[1][2] - bar[2][2]) < 1e-6                    # along a level soffit


def test_shallow_corbel_takes_only_the_secondary_bars_that_fit():
    shallow = dict(SLOPED, depth_face=200.0, depth_tip=200.0)
    out = cb.build(shallow, COLUMN, BARS)
    zs = sorted(u[0][2] for u in out['secondary'])
    assert all(b - a >= cb.layer_pitch_mm(10.0) - 1e-6 for a, b in zip(zs, zs[1:]))
    assert any(u'secondary' in n for n in out['notes'])
    bar = out['compression'][0]
    assert bar[0][2] - bar[1][2] >= 5 * 12.0                    # P = 5d down the outer face
