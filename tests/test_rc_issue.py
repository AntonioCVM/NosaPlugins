# -*- coding: utf-8 -*-
"""T9.13 RC drawing issue checks (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import rc_issue as ri  # noqa: E402


def test_placeholders_block_only_a_construction_issue():
    assert ri.is_placeholder(u'Author') and ri.is_placeholder(u'  ') and ri.is_placeholder(u'Client X')
    assert not ri.is_placeholder(u'A. Viñas')
    assert ri.for_construction(u'C01') and ri.for_construction(u'c02')
    assert not ri.for_construction(u'P01') and not ri.for_construction(u'PC01')


def test_one_mark_one_bending():
    bars = [(u'01', u'H20 00 4250'), (u'01', u'H20 00 4250'), (u'02', u'H10 51 1800'), (u'02', u'H10 51 1900')]
    assert ri.mark_conflicts(bars) == {u'02': [u'H10 51 1800', u'H10 51 1900']}


def test_overlapping_texts_and_drawing_refs():
    boxes = [(0, 0, 10, 5), (8, 2, 20, 6), (30, 0, 40, 5)]
    assert ri.overlaps(boxes) == [(0, 1)]
    assert ri.overlaps(boxes, gap=3.0) == []
    assert ri.drawing_refs(u'1000 series, see 1001 and 12345') == [u'1000', u'1001']


def test_gate_card():
    f = [ri.Finding(u'4003 - Beams', ri.WARNING, u'Texts', u'x'), ri.Finding(u'4002 - Cols', ri.PASSED, u'All', u'')]
    card = ri.gate(f)
    assert card['status'] == 'warn' and card['count'] == 1 and card['items'][1]['severity'] == u'PASS'
    assert ri.gate([ri.Finding(u'4003 - B', ri.ERROR, u'Bar marks', u'x')])['status'] == 'fail'
