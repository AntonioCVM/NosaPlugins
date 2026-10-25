# -*- coding: utf-8 -*-
"""bar_schedules — pure helpers (A4 BBS per drawing, identical members' copies)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NOSA.tab', 'Reinforcement.panel',
                                'RebarAutomate.pushbutton', 'lib'))
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
