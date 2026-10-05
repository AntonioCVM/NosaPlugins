# -*- coding: utf-8 -*-
"""T7.2 continuous beams: span order, supports, central-third laps, support bars (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import continuous_beam as cb  # noqa: E402

# three 6 m clear spans between 400 mm columns
SPANS = [{'id': 2, 'x0': 6400.0, 'x1': 12400.0}, {'id': 1, 'x0': 0.0, 'x1': 6000.0},
         {'id': 3, 'x0': 12800.0, 'x1': 18800.0}]


def test_spans_are_ordered_and_the_gaps_are_the_supports():
    ordered, supports, warnings = cb.order_spans(SPANS)
    assert [s['id'] for s in ordered] == [1, 2, 3] and not warnings
    assert [(s['x0'], s['x1'], s['width']) for s in supports] == [(6000.0, 6400.0, 400.0),
                                                                   (12400.0, 12800.0, 400.0)]


def test_a_wide_gap_is_not_one_support():
    _o, supports, warnings = cb.order_spans([{'id': 1, 'x0': 0.0, 'x1': 5000.0},
                                             {'id': 2, 'x0': 8000.0, 'x1': 12000.0}])
    assert not supports[0]['continuous'] and warnings


def test_support_bars_reach_a_quarter_of_the_longer_span_past_each_face():
    ordered, supports, _w = cb.order_spans(SPANS)
    assert cb.support_bar_range(supports[0], ordered[0], ordered[1]) == (4500.0, 7900.0)


def test_bottom_bars_enter_an_intermediate_support_ten_diameters():
    assert cb.bottom_anchor_into_support(16.0, 400.0) == (160.0, None)
    length, note = cb.bottom_anchor_into_support(20.0, 300.0)
    assert length == 140.0 and note


def test_hanger_laps_fall_in_the_central_third_of_a_span():
    ordered, _s, _w = cb.order_spans(SPANS)
    segments, warnings = cb.lap_cuts(-360.0, 19160.0, ordered, 12000.0, 800.0)
    assert not warnings and len(segments) == 2
    (a0, a1), (b0, b1) = segments
    assert a1 - a0 <= 12000.0 and b1 - b0 <= 12000.0 and abs((a1 - b0) - 800.0) < 1e-6
    centre = (a1 + b0) / 2.0
    span = [s for s in ordered if s['x0'] <= centre <= s['x1']][0]
    third = (span['x1'] - span['x0']) / 3.0
    assert span['x0'] + third <= centre <= span['x1'] - third


def test_no_lap_when_the_bar_fits_one_stock_length():
    segments, _w = cb.lap_cuts(0.0, 9000.0, SPANS, 12000.0, 800.0)
    assert segments == [(0.0, 9000.0)]


def test_support_bar_slots_fill_between_hangers_then_a_second_layer():
    assert cb.support_bar_slots(3, 2) == [('between', 0), ('between', 1)]
    assert cb.support_bar_slots(2, 1) == [('between', 0)]
    assert cb.support_bar_slots(2, 3) == [('between', 0), ('second', 0), ('second', 1)]
    assert cb.support_bar_slots(4, 1) == [('between', 1)]


def test_solid_spans_one_piece_is_one_span():
    assert cb.solid_spans([(0.0, 9550.0)], 9550.0) == [(0.0, 9550.0)]
    assert cb.solid_spans([], 6000.0) == [(0.0, 6000.0)]


def test_solid_spans_split_by_an_intermediate_column():
    # a 10 m beam over a 450 mm column at mid length: the solid comes in two pieces
    spans = cb.solid_spans([(4775.0, 9550.0), (0.0, 4325.0)], 9550.0)
    assert spans == [(0.0, 4325.0), (4775.0, 9550.0)]


def test_solid_spans_ignore_slivers_and_hairline_gaps():
    spans = cb.solid_spans([(0.0, 3000.0), (3004.0, 6000.0), (6000.0, 6020.0)], 6000.0)
    assert spans == [(0.0, 6000.0)]


def test_shift_rule_is_1125_d():
    assert abs(cb.shift_al_mm(700.0) - 787.5) < 1e-9


def test_hogging_bars_reach_015_and_030_l_plus_al():
    short, long_ = cb.hogging_reaches_mm(6000.0, 787.5)
    assert abs(short - 1687.5) < 1e-9 and abs(long_ - 2587.5) < 1e-9
    # never shorter than the anchorage length
    assert cb.hogging_reaches_mm(2000.0, 200.0, lbd_mm=900.0)[0] == 900.0


def test_hogging_bars_split_half_and_half():
    assert cb.hogging_groups(1) == (1, 0)
    assert cb.hogging_groups(2) == (1, 1)
    assert cb.hogging_groups(3) == (2, 1)


def test_end_support_top_bars_reach_02_l():
    assert cb.end_hogging_reach_mm(5000.0) == 1000.0


def test_sagging_bars_stop_008_l_from_an_end_and_020_l_from_an_internal_support():
    a, b = cb.sagging_range_mm(0.0, 5000.0, False, True)
    assert abs(a - 400.0) < 1e-9 and abs(b - 4000.0) < 1e-9
    a, b = cb.sagging_range_mm(0.0, 5000.0, True, True)
    assert abs(a - 1000.0) < 1e-9 and abs(b - 4000.0) < 1e-9
