# -*- coding: utf-8 -*-
"""T8.14: name rules of the standards audit."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))

from nosa_utils import standards_audit as sa  # noqa: E402


def test_spanish_import_imperial_and_render_names():
    assert sa.classify_name(u'Muro por defecto')
    assert sa.classify_name(u'Trazo punto')
    assert sa.classify_name(u'IMPORT-DASHDOT')
    assert sa.classify_name(u'Render Material 0-0-255')
    assert sa.classify_name(u'Hidden 1/8"')
    assert sa.classify_name(u'NOSA concrete cut (light orange)') == []
    assert sa.classify_name(u'Concrete - RC40/50') == []


def test_copies():
    assert sa.looks_like_copy(u'Stringer - 50 mm Width (1)')
    assert sa.looks_like_copy(u'NOSA Manual title /With scale 2')
    assert not sa.looks_like_copy(u'Schedule 40')
    assert not sa.looks_like_copy(u'Scale 1 2')
    assert not sa.looks_like_copy(u'Ceiling 1')
    assert not sa.looks_like_copy(u'Propylene Glycol - 10')


def test_duplicates_ignore_spaces_dashes_case():
    d = sa.duplicates([u'Phase - Demo', u'Phase-Demo', u'Long dash', u'Long Dash', u'Unique'])
    assert sorted(len(v) for v in d.values()) == [2, 2]
