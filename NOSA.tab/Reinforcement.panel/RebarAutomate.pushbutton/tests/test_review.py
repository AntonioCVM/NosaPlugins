# -*- coding: utf-8 -*-
"""T12.8 review: warnings grouped, audit summarised."""
from __future__ import print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))
import review  # noqa: E402


def test_same_warning_on_several_drawings_reads_once():
    msgs = [u"4501 Columns: modelled cover 40 mm differs from the general notes' 50mm.",
            u"4502 Slabs: modelled cover 40 mm differs from the general notes' 50mm.",
            u'4501: no bar schedules issued yet for this drawing.',
            u'4502: no bar schedules issued yet for this drawing.',
            u'Something else.']
    out = review.group_messages(msgs)
    assert out[0] == u"modelled cover 40 mm differs from the general notes' 50mm. (4501 Columns, 4502 Slabs)"
    assert out[1] == u'no bar schedules issued yet for this drawing. (4501, 4502)'
    assert out[2] == u'Something else.'


def test_summary_counts_the_audit_by_kind():
    issues = [{'sheet': u'4502', 'view': u'S1 Plan', 'category': u'A4', 'element': u'x', 'problem': u'crosses y'},
              {'sheet': u'4502', 'view': u'S1 Plan', 'category': u'A4', 'element': u'z', 'problem': u'crosses w'}]
    text, n = review.summary([], issues)
    assert n == 2 and u'A4 lines crossing: 2' in text
    text, n = review.summary([], [])
    assert n == 0 and u'no incidents' in text


def test_informative_crossings_not_counted():
    issues = [{'sheet': u'4504', 'view': u'W1', 'category': u'A4i', 'element': u'x', 'problem': u'across the member'},
              {'sheet': u'4504', 'view': u'W1', 'category': u'A4', 'element': u'y', 'problem': u'crosses'}]
    text, n = review.summary([], issues)
    assert n == 1 and u'(1 incident(s))' in text and u'A4i' in text


def test_a_calling_up_printing_another_mark_is_found():
    # 2026-10-24 audit: S3 plan '6H16-06(a to f) B2' for bars 03, '33H16-01(a to q) B1' for 01a..01ag
    assert review.callout_mismatch(u'6H16-06(a to f) B2', u'03', u'(a to f)') == u'06(a to f)'
    assert review.callout_mismatch(u'33H16-01(a to q) B1', u'01', u'(a to ag)') == u'01(a to q)'
    assert review.callout_mismatch(u'16H10-03-200 LINKS', u'04') == u'03'
    assert review.callout_mismatch(u'2H20-01', u'01') == u'' and review.callout_mismatch(u'01', u'01') == u''
    assert review.callout_mismatch(u'1H16-E07 T1', u'07') == u'' and review.callout_mismatch(u'LINKS', u'04') == u''
    assert review.callout_mismatch(u'06', u'06', u'(a to f)') == u''   # a section's mark alone
