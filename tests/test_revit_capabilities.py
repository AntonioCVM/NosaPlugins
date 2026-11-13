# -*- coding: utf-8 -*-
"""T8.55 Revit capability matrix (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import revit_capabilities as rc  # noqa: E402


class _Fake(object):
    pass


def test_flags_and_merge():
    DB, DBS = _Fake(), _Fake()
    DB.MultiReferenceAnnotation = object
    DBS.RebarCoupler = object
    flags = rc.api_flags(DB, DBS)
    assert flags[u'couplers'] and flags[u'multi_rebar_annotation'] and not flags[u'terminations']
    matrix = rc.merge({}, 2024, flags, {u'couplers': (u'fail', u'probe')})
    assert rc.supports(2024, u'couplers', matrix) is False                 # the live probe wins
    assert rc.supports(2024, u'multi_rebar_annotation', matrix) is True
    assert rc.supports(2026, u'couplers', matrix) is None


def test_matrix_file_is_valid():
    matrix = rc.load_matrix()
    assert u'versions' in matrix and isinstance(matrix.get(u'known_defects', []), list)
