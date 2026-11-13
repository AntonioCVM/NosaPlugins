# -*- coding: utf-8 -*-
"""T8.51 welded fabric to BS 4483 (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import fabric  # noqa: E402


def test_catalogue_areas():
    main, cross = fabric.area_per_m(u'A193')
    assert abs(main - 192.4) < 0.5 and abs(cross - 192.4) < 0.5
    main, cross = fabric.area_per_m(u'B785')
    assert abs(main - 785.4) < 0.5 and abs(cross - 251.3) < 0.5
    assert fabric.references(u'A')[0] == u'A393'


def test_laps():
    assert fabric.secondary_lap_mm(6.0, 400.0) == 400.0
    assert fabric.secondary_lap_mm(5.0, 200.0) == 200.0
    assert fabric.secondary_lap_mm(8.0, 200.0) == 400.0
    assert fabric.secondary_lap_mm(10.0, 100.0) == 350.0
    main, cross = fabric.laps_mm(u'A193')
    assert main == cross and main >= 300.0                     # 300 mm minimum lap
    main, cross = fabric.laps_mm(u'B785')
    assert cross == 400.0 and main > cross


def test_sheets_and_choice():
    assert fabric.sheets(4800.0, 2400.0, 300.0, 300.0) == 1
    assert fabric.sheets(9000.0, 4500.0, 300.0, 300.0) == 2 * 2
    assert fabric.lightest(190.0, 190.0) == u'A193' and fabric.lightest(190.0) == u'C283'
    assert fabric.lightest(600.0, 200.0) == u'B785'
    assert fabric.lightest(2000.0) is None


def test_schedule_rows():
    rows = fabric.schedule_rows([(u'S2', u'F2', u'A193', 3), (u'S1', u'F1', u'A142', 2)])
    assert rows[0][:5] == (u'S1', u'F1', u'A142', u'4800 x 2400', 2)
    assert 20.0 < rows[1][5] / 3.0 < 40.0                      # an A193 sheet is about 35 kg
