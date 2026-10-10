# -*- coding: utf-8 -*-
"""T8.52 mechanical couplers (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import couplers  # noqa: E402


def test_types_and_marks():
    assert couplers.type_name(20.0) == u'H20' and couplers.type_name(50.0) is None
    assert couplers.mark_with_end_prep(u'03', True) == u'E03'
    assert couplers.mark_with_end_prep(u'E03', True) == u'E03'
    assert couplers.mark_with_end_prep(u'E03', False) == u'03'
    assert couplers.mark_with_end_prep(u'', True) == u''


def test_joints():
    assert couplers.joints_mm([3000.0, 6000.0], 75.0) == [3575.0, 6575.0]
