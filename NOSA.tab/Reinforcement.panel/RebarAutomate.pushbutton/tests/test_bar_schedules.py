# -*- coding: utf-8 -*-
"""bar_schedules (T8.33/T8.34): SMDSC 4.5.1 references, A4 packing, BS 8666 rounding."""
from __future__ import print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'lib'))
import bar_schedules as bs


def test_schedule_reference_is_drawing_schedule_revision():
    assert bs.schedule_key(u'4002', 1) == u'4002-01'
    assert bs.schedule_ref(u'4002-01', u'A') == u'4002-01-A'
    assert bs.schedule_ref(u'4002-01', u'') == u'4002-01'
    print(u'[PASS] test_schedule_reference_is_drawing_schedule_revision')


def test_members_stay_whole_and_pages_fill_in_order():
    pages = bs.pack([(u'C1', 10), (u'C2', 10), (u'C3', 10), (u'B1', 50), (u'F1', 3)], capacity=46)
    assert pages == [[u'C1', u'C2', u'C3'], [u'B1'], [u'F1']]
    print(u'[PASS] test_members_stay_whole_and_pages_fill_in_order')


def test_plan_numbers_schedules_per_drawing_level_by_level():
    keys = bs.plan({u'4002': [(3.0, u'C10', 20), (0.0, u'C9', 20), (0.0, u'C2', 5)],
                    u'4001': [(0.0, u'F1', 4)]}, capacity=46)
    assert keys[u'F1'] == u'4001-01'
    assert keys[u'C2'] == u'4002-01' and keys[u'C9'] == u'4002-01'   # ground floor first
    assert keys[u'C10'] == u'4002-02'                                   # next level, next page
    print(u'[PASS] test_plan_numbers_schedules_per_drawing_level_by_level')


def test_marks_unique_within_a_schedule_identical_bars_shared():
    bars = [((0, u'B1-1'), 1, u'top', u'a'), ((0, u'B1-1'), 2, u'link', u'b'),
            ((0, u'B1-2'), 1, u'mid', u'c'), ((0, u'B1-2'), 2, u'link', u'd'),
            ((0, u'B1-3'), 1, u'top', u'e')]
    marks = bs.schedule_marks(bars)
    assert marks == {u'a': 1, u'b': 2, u'c': 3, u'd': 2, u'e': 1}
    print(u'[PASS] test_marks_unique_within_a_schedule_identical_bars_shared')


def test_natural_order_of_members():
    assert sorted([u'C10', u'C9', u'C1'], key=bs.natural_key) == [u'C1', u'C9', u'C10']
    print(u'[PASS] test_natural_order_of_members')


def test_bs8666_rounding():
    import rebar_schedule as rs
    assert rs.bs8666_length_mm(5301) == 5325 and rs.bs8666_length_mm(5300) == 5300
    assert rs.bs8666_dim(u'602') == u'600' and rs.bs8666_dim(u'608') == u'610'
    rows = rs.bbs_rows([{'member': u'F1', 'mark': u'01', 'diameter_mm': 16, 'count': 2, 'members': 1,
                         'unit_length_mm': 1210.4, 'shape_code': u'21',
                         'shape_params': u'A=302;B=608;C=302;R=32', 'total_weight_kg': 3.8}])
    assert rows[0][6] == u'1225'
    assert rows[0][8:11] == [u'300', u'610', u'300'] and rows[0][14] == u'32'
    print(u'[PASS] test_bs8666_rounding')


def test_drawing_marks_keep_the_marks_the_calling_ups_carry():
    # 2026-10-24 audit, drawing 4502: S1 and S3 on two schedules, marks already unique on the drawing
    bars = [((u'4502-01', 0, u'S1'), 1, u'straight 7875', u'a'), ((u'4502-01', 0, u'S1'), 6, u'straight 2375', u'b'),
            ((u'4502-02', 0, u'S3'), 12, (u'varying', 1), u'c'), ((u'4502-02', 0, u'S3'), 13, u'straight 4875', u'd')]
    assert bs.drawing_marks(bars) == {u'a': 1, u'b': 6, u'c': 12, u'd': 13}
    print(u'[PASS] test_drawing_marks_keep_the_marks_the_calling_ups_carry')


def test_drawing_marks_renumber_a_mark_naming_two_bars():
    # 4501: the copies' links still '03' (the circular link's mark) though they are the original's '04'
    bars = [((u'4501-01', 0, u'C1'), 1, u'H20', u'v'), ((u'4501-01', 0, u'C2'), 3, u'circular', u'c5'),
            ((u'4501-01', 0, u'C3'), 4, u'link 365', u'c1'), ((u'4501-01', 0, u'C3'), 3, u'link 365', u'copy')]
    marks = bs.drawing_marks(bars)
    assert marks[u'c1'] == marks[u'copy'] and marks[u'c5'] != marks[u'copy']
    assert len(set(marks.values())) == 3
    print(u'[PASS] test_drawing_marks_renumber_a_mark_naming_two_bars')




if __name__ == '__main__':
    test_schedule_reference_is_drawing_schedule_revision()
    test_members_stay_whole_and_pages_fill_in_order()
    test_plan_numbers_schedules_per_drawing_level_by_level()
    test_marks_unique_within_a_schedule_identical_bars_shared()
    test_natural_order_of_members()
    test_bs8666_rounding()
    test_drawing_marks_keep_the_marks_the_calling_ups_carry()
    test_drawing_marks_renumber_a_mark_naming_two_bars()


def test_bar_schedule_sheets_are_filed_in_rc_schedules():
    import rebar_views
    assert rebar_views.sheet_package(u'5500') == u"5500's - RC schedules"       # user 2026-10-24
    assert rebar_views.sheet_package(u'5512') == u"5500's - RC schedules"
    assert rebar_views.sheet_package(u'4503') == u"4500's - RC details"
    assert rebar_views.sheet_package(u'') == rebar_views.RC_PACKAGE
    print(u'[PASS] test_bar_schedule_sheets_are_filed_in_rc_schedules')


def test_schedules_left_without_bars():
    # m6 (2026-10-25, Revit 2025): PC10 joined drawing 4505, so 'BBS 4506-01' was left empty
    names = [u'BBS', u'BBS 4505-01', u'BBS 4506-01', u'BBS 4506-01 copy', u'Rebar schedule']
    assert bs.stale_schedules(names, set([u'4505-01'])) == [u'BBS 4506-01']
    assert bs.stale_schedules(names, set([u'4505-01', u'4506-01'])) == []
    print(u'[PASS] test_schedules_left_without_bars')
