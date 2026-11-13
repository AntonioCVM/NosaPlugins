# -*- coding: utf-8 -*-
"""T9.14 RC revision register (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import rc_register as rr  # noqa: E402


def _bar(mark, count=4, length=4250, size=u'20', shape=u'00'):
    return {u'mark': mark, u'size': size, u'shape': shape, u'length': length, u'count': count}


def test_changes_between_issues():
    old = {u'a': _bar(u'01'), u'b': _bar(u'02'), u'c': _bar(u'03')}
    new = {u'a': _bar(u'01', count=5), u'c': _bar(u'03'), u'd': _bar(u'04', size=u'16')}
    changes = rr.diff(old, new)
    assert [c[0] for c in changes] == [u'changed', u'removed', u'added']
    assert changes[0][2] == u'01: number 4 to 5'
    assert u'02 4H20 00 removed' == changes[1][2] and changes[2][2] == u'04 4H16 00 added'
    text = rr.table(u'P02', changes)
    assert text.startswith(u'REINFORCEMENT CHANGES - REVISION P02') and u'- 01: number 4 to 5' in text
    assert u'No change' in rr.table(u'P03', [])


def test_records_kept_per_drawing_and_revision():
    root = tempfile.mkdtemp()
    try:
        assert rr.last(u'Model', u'4003', root=root) == (None, {})
        rr.save(u'Model', u'4003', u'P01', {u'a': _bar(u'01')}, root)
        rr.save(u'Model', u'4003', u'P02', {u'a': _bar(u'01', count=6)}, root)
        rr.save(u'Model', u'4003', u'C01', {u'a': _bar(u'01', count=6)}, root)
        folder = rr.folder(u'Model', u'4003', root)
        for k, rev in enumerate((u'P01', u'P02', u'C01')):
            os.utime(os.path.join(folder, rev + u'.json'), (1000 + k, 1000 + k))
        assert rr.last(u'Model', u'4003', root=root)[0] == u'C01'          # issued last, though it sorts first
        rev, rec = rr.last(u'Model', u'4003', before=u'C01', root=root)    # re-issuing C01: against P02
        assert rev == u'P02' and rec[u'a'][u'count'] == 6
    finally:
        shutil.rmtree(root)
