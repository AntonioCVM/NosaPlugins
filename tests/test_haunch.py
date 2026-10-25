# -*- coding: utf-8 -*-
"""nosa_utils.haunch — links of a haunched beam (T8.58)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import haunch  # noqa: E402


def test_a_straight_beam_keeps_one_set_per_zone():
    assert haunch.depth_runs([50.0, 250.0, 450.0], [0.0, 0.0, 2.0]) == [([50.0, 250.0, 450.0], 0.0)]


def test_haunch_links_one_per_depth_then_the_set():
    # 300 deep over 1000 mm at the start: the links there step down, the rest stay one set
    pos = [50.0, 250.0, 450.0, 650.0, 850.0, 1050.0, 1250.0]
    drops = [max(0.0, 300.0 * (1000.0 - d) / 1000.0) for d in pos]
    runs = haunch.depth_runs(pos, drops)
    assert [r[1] for r in runs] == [285.0, 225.0, 165.0, 105.0, 45.0, 0.0]
    assert runs[-1] == ([1050.0, 1250.0], 0.0)


def test_equal_depths_share_a_run_and_both_ends_are_split():
    runs = haunch.depth_runs([0.0, 100.0, 200.0, 300.0, 400.0], [100.0, 101.0, 0.0, 0.0, 60.0])
    assert runs == [([0.0, 100.0], 100.0), ([200.0, 300.0], 0.0), ([400.0], 60.0)]
