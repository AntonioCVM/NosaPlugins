# -*- coding: utf-8 -*-
"""T7.3 Create Views: scale choice, sheet packing, sheet numbers (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import view_plan as vp  # noqa: E402


def test_member_sections_at_smdsc_1_20():
    assert vp.choose_scale('member_section', 600.0, 800.0) == 20
    assert vp.choose_scale('member_section', 1200.0, 3000.0) == 20
    assert vp.choose_scale('member_section', 3000.0, 8000.0) == 50


def test_elevations_at_smdsc_1_50_stepping_up_when_tall():
    assert vp.choose_scale('column_elevation', 1000.0, 3500.0) == 50
    assert vp.choose_scale('column_elevation', 1000.0, 24000.0) == 50
    assert vp.choose_scale('column_elevation', 1000.0, 60000.0) == 100
    assert vp.choose_scale('elevation', 9000.0, 900.0) == 50


def test_slab_sections_and_plans():
    assert vp.choose_scale('slab_section', 8000.0, 600.0) == 50
    assert vp.choose_scale('slab_section', 40000.0, 600.0) == 100
    assert vp.choose_scale('plan', 15000.0, 12000.0) == 50
    assert vp.choose_scale('plan', 60000.0, 30000.0) == 200


def _overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_layout_keeps_views_apart_and_inside_the_area():
    sizes = [(200.0, 274.0), (250.0, 534.0), (150.0, 534.0), (200.0, 200.0)]
    placed = vp.layout(sizes)
    rects = []
    for (w, h), (sheet, cx, cy) in zip(sizes, placed):
        assert sheet == 0
        r = (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)
        assert vp.A1_AREA[0] - 1e-6 <= r[0] and r[2] <= vp.A1_AREA[2] + 1e-6
        assert vp.A1_AREA[1] - 1e-6 <= r[1] and r[3] <= vp.A1_AREA[3] + 1e-6
        rects.append(r)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _overlap(rects[i], rects[j])


def test_overflow_opens_a_second_sheet():
    placed = vp.layout([(660.0, 534.0), (660.0, 534.0)])
    assert [p[0] for p in placed] == [0, 1]


def test_next_sheet_numbers_skip_the_taken_ones():
    assert vp.next_sheet_numbers(['4000', '4001', '4003'], 3) == ['4002', '4004', '4005']


def test_coarser_scale_steps_through_the_candidates():
    assert vp.coarser_scale('elevation', 50) == 100
    assert vp.coarser_scale('elevation', 100) is None
    assert vp.coarser_scale('member_section', 20) == 50
