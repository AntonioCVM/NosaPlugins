# -*- coding: utf-8 -*-
"""T9.22: every registered detailing rule equals the constant the code uses, with its 4th-edition clause."""
from __future__ import absolute_import, division, print_function, unicode_literals
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import smdsc_rules  # noqa: E402


def test_register_matches_the_code():
    for module, constant, value, clause, _change in smdsc_rules.REGISTER:
        mod = importlib.import_module('nosa_utils.' + module)
        assert getattr(mod, constant) == value, (module, constant, getattr(mod, constant), value)
        assert clause


def test_citations_and_changes():
    assert smdsc_rules.citation(u'mesh_rules', u'TOP_BAR_SPAN_SHARE') == u'SMDSC 4th ed. MD S1'
    assert smdsc_rules.citation(u'mesh_rules', u'BAND_FACTOR').startswith(u'3rd ed.')
    assert smdsc_rules.citation(u'links', u'NOPE') == u''
    assert any(name == u'links.SIDE_BARS_DEPTH_MM' for name, _c, _x in smdsc_rules.changes())
