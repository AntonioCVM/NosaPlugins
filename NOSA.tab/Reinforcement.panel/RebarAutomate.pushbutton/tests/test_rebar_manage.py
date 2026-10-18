# -*- coding: utf-8 -*-
"""Phase 11: layer groups, issue log and identical members (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

import rebar_manage as rm  # noqa: E402


def test_layer_groups():
    assert rm.layer_groups(u'bottom_x', u'B1') == set([u'B1'])
    assert rm.layer_groups(u'trimmer_bottom', u'B2') == set([u'B2', u'OPENING'])
    assert rm.layer_groups(u'corner_ubar', u'') == set([u'UBAR'])
    assert rm.layer_groups(u'dowel', u'') == set([u'STARTER'])
    assert rm.layer_groups(u'starter_link', u'') == set([u'STARTER', u'LINK'])
    assert u'N1' in rm.layer_groups(u'vertical', u'N1')


def test_marks():
    assert rm.parse_marks(u'01, 3;05  S1-02') == [u'01', u'3', u'05', u'S1-02']
    assert rm.mark_matches(u'01', [u'1']) and rm.mark_matches(u'S1-01', [u'01'])
    assert rm.mark_matches(u's1-01', [u'S1-01']) and not rm.mark_matches(u'02', [u'01'])
    assert not rm.mark_matches(u'', [u'01'])
    assert rm.layer_groups(u'closure_x', u'B1') == set([u'B1', u'UBAR'])


def test_revisions_and_changes():
    assert rm.next_revision(u'') == u'A' and rm.next_revision(u'A') == u'B'
    assert rm.next_revision(u'Z') == u'AA' and rm.next_revision(u'AZ') == u'BA'
    before = {u'01': [20, 16, 4200.0], u'02': [10, 12, 3000.0]}
    after = {u'01': [22, 16, 4200.0], u'03': [4, 20, 1500.0]}
    changes = rm.snapshot_changes(before, after)
    assert changes == [u'01 number 20 -> 22', u'02 removed', u'03 added (4 H20 x 1500)']
    text = rm.history_text([{'revision': u'A', 'status': u'P', 'date': u'2026-10-18', 'bars': before},
                            {'revision': u'B', 'status': u'C', 'date': u'2026-10-19', 'bars': after,
                             'changes': changes}])
    assert text.splitlines()[0].startswith(u'B C 2026-10-19 - 2 mark(s): 01 number')
    assert rm.history_text([]) == u'Not issued yet.'


def test_same_member():
    assert rm.same_member((5, (6000.0, 300.0, 600.0)), (5, (6001.0, 300.0, 600.0)))
    assert not rm.same_member((5, (6000.0, 300.0, 600.0)), (6, (6000.0, 300.0, 600.0)))
    assert not rm.same_member((5, (6000.0, 300.0, 600.0)), (5, (6100.0, 300.0, 600.0)))


if __name__ == '__main__':
    test_layer_groups()
    test_marks()
    test_revisions_and_changes()
    test_same_member()
    print('test_rebar_manage: OK')
