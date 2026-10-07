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


if __name__ == '__main__':
    test_schedule_reference_is_drawing_schedule_revision()
    test_members_stay_whole_and_pages_fill_in_order()
    test_plan_numbers_schedules_per_drawing_level_by_level()
    test_natural_order_of_members()
    test_bs8666_rounding()
