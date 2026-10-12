# -*- coding: utf-8 -*-
"""T9.15 rule-added bars flag (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import rule_flags as rf  # noqa: E402


def test_rule_added_layers_are_flagged_design_bars_are_not():
    assert u'MD OP1' in rf.rule_for(u'trimmer_bottom')
    assert rf.flag_text(u'side').endswith(u'confirm with design')
    for design in (u'top', u'bottom_x', u'stirrup', u'vertical', u'', None):
        assert rf.rule_for(design) == u'' and rf.flag_text(design) == u''
