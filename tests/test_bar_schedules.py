# -*- coding: utf-8 -*-
"""bar_schedules — pure helpers (A4 BBS per drawing, identical members' copies)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NOSA.tab', 'Reinforcement.panel',
                                'RebarAutomate.pushbutton', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
import bar_schedules as bs  # noqa: E402


def test_copies_are_scheduled_on_their_originals_drawing():
    # 4-storey test 2026-10-25: F1 to F9 identical, the original's bars stamped 4501, the copies drawn on 4502-4505
    members = {u'4501': {u'F1 to F9': 1}, u'4506': {u'C1 to C27': 1}, u'4514': {u'C28 to C36': 1}}
    assert bs.homes(members) == {u'F1 to F9': u'4501', u'C1 to C27': u'4506', u'C28 to C36': u'4514'}


def test_a_member_on_two_drawings_stays_with_the_first():
    assert bs.homes({u'4510': {u'B1': 1}, u'4509': {u'B1': 1}}) == {u'B1': u'4509'}


def test_schedule_keys():
    assert bs.schedule_key(u'4501', 1) == u'4501-01'
    assert bs.schedule_ref(u'4501-01', u'A') == u'4501-01-A'
    assert bs.natural_key(u'C10') > bs.natural_key(u'C9')


def test_a_typical_details_sheet_names_no_schedules():
    import rc_legends
    text, warnings = rc_legends.drawing_notes(u'4515', {}, {}, schedule_refs=(), bars=False)
    assert u'none, no bars are detailed on this drawing' in text and u'to be issued' not in text
    assert not [w for w in warnings if u'no bar schedules' in w]
    text, warnings = rc_legends.drawing_notes(u'4516', {}, {}, schedule_refs=())
    assert u'to be issued (refs 4516-01' in text and [w for w in warnings if u'no bar schedules' in w]


def test_a_mark_is_one_bbs_length():
    import rebar_marking as rm
    assert rm.bbs_length_mm(4600.0) == 4600 and rm.bbs_length_mm(4600.0004) == 4600 and rm.bbs_length_mm(4600.3) == 4625
    assert rm.bbs_length_mm(4601.0) == 4625 and rm.bbs_length_mm(4624.6) == 4625
    assert rm.bbs_length_mm(5360.0) == rm.bbs_length_mm(5361.0) == 5375
