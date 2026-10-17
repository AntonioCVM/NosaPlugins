# -*- coding: utf-8 -*-
"""T9.21 NOSA typical details: which a drawing calls for, names, references."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import typical_details as td  # noqa: E402


def test_needed_by_case():
    assert td.needed(['floor'], [u'bottom_x', u'trimmer_bottom', u'diagonal_bottom', u'end_ubar']) == [u'S3', u'OP1']
    assert td.needed(['floor'], [u'top_x', u'bottom_x']) == [u'S1']
    assert td.needed(['wall'], [u'vertical', u'trimmer', u'opening_ubar']) == [u'W4']
    assert td.needed(['foundation'], [u'bottom_x', u'dowel'], piled=True) == [u'C1', u'PC1']
    assert td.needed(['beam'], [u'top', u'bottom', u'stirrup']) == []


def test_every_detail_cites_the_4th_edition_in_english():
    for key, title, md, sketch in td.DETAILS:
        assert md.startswith(u'SMDSC 4th ed. MD ') and title == title.upper()
        assert td.view_name(key).startswith(td.PREFIX + key + u' - ')
        texts = [d[2] for kind, d in sketch if kind == 'text']
        assert texts and all(t.isascii() for t in texts)
