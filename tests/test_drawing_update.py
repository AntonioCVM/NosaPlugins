# -*- coding: utf-8 -*-
"""drawing_update (T12.9): what an update keeps, lays out again or drops."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import drawing_update as du  # noqa: E402

SIG = {'7': du.bar_signature(5, 6050.0, 11, 22)}


def _entry(points, sig=None, bars=('7',)):
    return {'bars': list(bars), 'points': points, 'sig': {'7': sig or SIG['7']}}


def test_unmoved_annotation_is_laid_out_again():
    e = _entry([(0.0, 0.0), (100.0, 0.0)])
    assert du.tag_action(e, [(10.0, 0.0), (100.0, 0.0)], SIG, 50) == du.RELAY        # 0.2 mm on paper at 1:50


def test_moved_tag_of_unchanged_bar_is_kept():
    e = _entry([(0.0, 0.0)])
    assert du.tag_action(e, [(500.0, 0.0)], SIG, 50) == du.KEEP                       # 10 mm on paper


def test_moved_tag_of_changed_bar_is_laid_out_again():
    e = _entry([(0.0, 0.0)], sig=du.bar_signature(4, 6050.0, 11, 22))
    assert du.tag_action(e, [(500.0, 0.0)], SIG, 50) == du.RELAY


def test_tag_of_deleted_bar():
    e = _entry([(0.0, 0.0)], bars=('8',))
    assert du.tag_action(e, [(0.0, 0.0)], SIG, 50) == du.GONE
    assert du.tag_action(e, [(500.0, 0.0)], SIG, 50) == du.GONE_MOVED


def test_kept_once_stays_kept():
    e = dict(_entry([(0.0, 0.0)]), kept=True)
    assert du.tag_action(e, [(0.0, 0.0)], SIG, 50) == du.KEEP


def test_moved_plugin_note_without_bars_is_kept():
    e = {'bars': [], 'points': [(0.0, 0.0), (10.0, 10.0)], 'sig': {}}
    assert du.tag_action(e, [(300.0, 0.0), (310.0, 10.0)], SIG, 50) == du.KEEP
    assert du.tag_action(e, [(0.0, 0.0), (10.0, 10.0)], SIG, 50) == du.RELAY


def test_view_and_viewport_changes():
    rec = {'crop': [0.0, 0.0, 1000.0, 500.0], 'scale': 50, 'centre': [400.0, 300.0]}
    assert du.view_changed(rec, [0.0, 0.0, 1000.0, 500.0], 50) == (False, False)
    assert du.view_changed(rec, [0.0, 0.0, 1200.0, 500.0], 20) == (True, True)
    assert du.view_changed({}, [0.0, 0.0, 1.0, 1.0], 20) == (False, False)              # no record: nothing known
    assert not du.viewport_moved(rec, [400.4, 300.0]) and du.viewport_moved(rec, [420.0, 300.0])


def test_record_round_trip():
    rec = {'kind': 'beam', 'notes': {'12': _entry([(1.0, 2.0)])}}
    back = du.decode(du.encode(rec))
    assert back['kind'] == 'beam' and back['notes']['12']['bars'] == ['7']
    assert du.decode(u'') == {} and du.decode(u'{bad') == {} and du.decode(u'{"v": 99}') == {}


def test_sheet_numbers_old_first_and_never_shared_twice():
    shared = ['4507', '4508']
    pool = du.NumberPool(['4502', '4503'], shared)
    assert [pool.pop(0) for _ in range(3)] == ['4502', '4503', '4507'] and shared == ['4508']


def test_update_keeps_marks_and_numbers_new_bars():
    known, todo = du.keep_marks([(1, 1, 'a'), (2, 2, 'b'), (3, 0, 'c'), (4, 1, 'a'), (5, 2, 'd')])
    assert known == {'a': 1, 'b': 2}
    assert todo == [3, 5]                     # new bar, and a bar whose mark another kind of bar holds


def test_users_changes_stay_theirs_on_the_next_update():
    rec = {'crop': [0.0, 0.0, 1200.0, 500.0], 'scale': 20, 'centre': [420.0, 300.0],
           'user_crop': True, 'user_scale': True, 'user_place': True}
    assert du.view_changed(rec, [0.0, 0.0, 1200.0, 500.0], 20) == (True, True)       # unchanged since: still theirs
    assert du.viewport_moved(rec, [420.0, 300.0])


def test_issue_dates_read_dd_mm_yy():
    import datetime
    assert du.issue_date(datetime.date(2026, 10, 25)) == u'25/10/26'
    assert du.from_revit_date(u'10/24/26') == u'24/10/26'           # Revit's own m/d/yy
    assert du.from_revit_date(u'1/5/2026') == u'05/01/26'
    assert du.from_revit_date(u'25/10/26') is None                  # not Revit's: kept as written
    assert du.from_revit_date(u'Oct 2026') is None and du.from_revit_date(u'') is None
