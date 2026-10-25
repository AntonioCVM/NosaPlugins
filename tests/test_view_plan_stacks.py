# -*- coding: utf-8 -*-
"""view_plan — column stacks drawn as one continuous elevation (user 2026-10-25) and range labels."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'NOSA.tab', 'Reinforcement.panel',
                                'RebarAutomate.pushbutton', 'lib'))
import view_plan as vp  # noqa: E402


def _col(key, x, y, z0, z1, half=225.0):
    return (key, (x - half, y - half, x + half, y + half), z0, z1)


def test_four_storeys_on_two_grids_make_two_stacks():
    items = [_col(u'a%d' % k, 0, 0, 3000 * k, 3000 * (k + 1)) for k in range(4)] + \
            [_col(u'b%d' % k, 6000, 0, 3000 * k, 3000 * (k + 1)) for k in range(4)]
    assert vp.column_stacks(items) == [[u'a0', u'a1', u'a2', u'a3'], [u'b0', u'b1', u'b2', u'b3']]


def test_a_column_changing_size_stays_on_its_stack():
    items = [_col(u'low', 0, 0, 0, 3000, 300.0), _col(u'up', 75, 0, 3000, 6000, 200.0)]
    assert vp.column_stacks(items) == [[u'low', u'up']]


def test_a_gap_or_a_shift_starts_a_new_stack():
    items = [_col(u'a', 0, 0, 0, 3000), _col(u'b', 0, 0, 3500, 6000), _col(u'c', 2000, 0, 3000, 6000)]
    assert vp.column_stacks(items) == [[u'a'], [u'b'], [u'c']]


def test_range_labels_hold_the_members_between():
    assert vp.holds(u'C1-C4', u'C3') and vp.holds(u'C1-C4', u'C4') and not vp.holds(u'C1-C4', u'C5')
    assert vp.holds(u'B3-B4', u'B3') and not vp.holds(u'B3-B4', u'C3')
    assert not vp.holds(u'C1-C4', u'C10')
    assert vp.stack_label([u'C1', u'C2', u'C3']) == u'C1-C3'
    assert vp.stack_label([u'C1', u'C1', u'C1']) == u'C1'
