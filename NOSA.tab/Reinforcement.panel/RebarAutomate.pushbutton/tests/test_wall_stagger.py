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
