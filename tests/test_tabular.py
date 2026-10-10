# -*- coding: utf-8 -*-
"""T8.54 tabular method (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import tabular  # noqa: E402


def test_bar_texts():
    assert tabular.bar_text(8, 25.0, u'03') == u'8H25-03'
    assert tabular.bar_text(14, 8.0, u'07', 200.0) == u'14H8-07-200'
    assert tabular.summarise([(3, 25.0, u'01', None), (3, 25.0, u'01', None), (2, 25.0, u'02', None)]) == \
        u'6H25-01 + 2H25-02'
    assert tabular.summarise([(14, 8.0, u'07', 200.0), (6, 8.0, u'07', 120.0)]) == u'6H8-07-120 + 14H8-07-200'


def test_groups():
    members = [(u'A3', (u'450x450', u'8H25-01')), (u'A1', (u'450x450', u'8H25-01')),
               (u'B2', (u'600x600', u'12H32-02')), (u'A10', (u'450x450', u'8H25-01'))]
    rows = tabular.groups(members)
    assert rows[0][1] == [u'A1', u'A3', u'A10'] and rows[1][1] == [u'B2']
    assert tabular.references_text(rows[0][1]) == u'A1, A3, A10'
