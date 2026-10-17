# -*- coding: utf-8 -*-
"""T7.6 — staggered laps in wall meshes: alternate bars, shorter first bar."""
from __future__ import print_function
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'lib'))

_autodesk = types.ModuleType('Autodesk'); _revit = types.ModuleType('Autodesk.Revit')
_revit.DB = types.ModuleType('Autodesk.Revit.DB'); _autodesk.Revit = _revit
sys.modules.setdefault('Autodesk', _autodesk); sys.modules.setdefault('Autodesk.Revit', _revit)
sys.modules.setdefault('Autodesk.Revit.DB', _revit.DB)

import wall_rebar as wr


def test_stagger_first_is_whole_25mm_under_stock_minus_1_3_lap():
    first = wr.stagger_first_mm(12000.0, 700.0)
    assert first == 11075.0
    assert first % 25 == 0 and first <= 12000.0 - 1.3 * 700.0


def test_parity_layouts_even_count():
    assert wr.parity_layouts(10, 200.0) == [(0.0, 5, 1600.0), (200.0, 5, 1600.0)]


def test_parity_layouts_odd_count_gives_extra_bar_to_first_row():
    a, b = wr.parity_layouts(7, 150.0)
    assert a == (0.0, 4, 900.0) and b == (150.0, 3, 600.0)
    assert a[1] + b[1] == 7


def test_parity_layouts_two_bars_are_single_bar_rows():
    assert wr.parity_layouts(2, 200.0) == [(0.0, 1, 0.0), (200.0, 1, 0.0)]


def test_lap_centres_are_never_in_the_same_section():
    stock, lap = 12000.0, 800.0
    first = wr.stagger_first_mm(stock, lap)
    centre_a = stock - lap / 2.0
    centre_b = first - lap / 2.0
    assert centre_a - centre_b >= wr.STAGGER_FACTOR * lap


def test_side_trimmers_cross_head_trimmers_in_contact():
    heads = [(84.0, 16.0), (-84.0, 16.0)]                       # 300 wall, head trimmers 84 mm off centre
    a = wr.crossing_depth_mm(73.0, 16.0, heads)                 # 11 mm from the head trimmer: through it
    assert abs(a - (84.0 - 17.6)) < 1e-6
    b = wr.crossing_depth_mm(-73.0, 16.0, heads)
    assert abs(b - (-84.0 + 17.6)) < 1e-6
    assert wr.crossing_depth_mm(40.0, 16.0, heads) == 40.0      # already clear
    c = wr.crossing_depth_mm(0.0, 20.0, [(0.0, 20.0)])          # thin wall, one bar each in the middle
    assert abs(c - 22.0) < 1e-6


def test_hole_ubars_beside_the_cut_rows():
    spots = wr.beside_rows_mm([1900.0, 2100.0, 2300.0, 2500.0], 2000.0, 2600.0, 12.0, 12.0)
    assert [round(x, 1) for x in spots] == [2113.2, 2313.2, 2513.2]
    assert wr.beside_rows_mm([1900.0], 2000.0, 2600.0, 12.0, 12.0) == []


def test_trimmer_clear_of_mesh_rows():
    from nosa_utils import mesh_rules
    z = mesh_rules.clear_of_rows([2140.0], [2096.0, 2296.0], 16.0, 12.0, 1.0)[0]
    assert all(abs(z - r) >= 1.1 * 14.0 + 25.0 - 1e-6 for r in (2096.0, 2296.0))
