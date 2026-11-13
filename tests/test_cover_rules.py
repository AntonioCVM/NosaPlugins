# -*- coding: utf-8 -*-
"""T12.5: the higher-ranked member's cover governs at a junction."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import cover_rules as cr  # noqa: E402


def test_higher_rank_governs():
    assert cr.governing_cover('beam', 30.0, 'column', 40.0) == 40.0      # a beam's bars into a column
    assert cr.governing_cover('column', 40.0, 'beam', 30.0) == 40.0      # a column's into a beam keep its own
    assert cr.governing_cover('slab', 25.0, 'wall', 35.0) == 35.0
    assert cr.governing_cover('wall', 35.0, 'foundation', 50.0) == 50.0
    assert cr.governing_cover('beam', 30.0, None, 50.0) == 30.0
    assert cr.governing_cover('beam', 30.0, 'column', None) == 30.0


def test_ranks_in_order():
    order = ['foundation', 'wall', 'column', 'beam', 'slab']
    assert [cr.rank(k) for k in order] == sorted([cr.rank(k) for k in order], reverse=True)
