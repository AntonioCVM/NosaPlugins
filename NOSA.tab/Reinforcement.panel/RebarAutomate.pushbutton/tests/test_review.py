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
