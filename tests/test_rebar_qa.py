# -*- coding: utf-8 -*-
"""T8.48 reinforcement QA rules (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import rebar_qa as qa  # noqa: E402


def test_cover():
    assert qa.cover_issues(40.0, 16.0, 40.0) == []
    assert qa.cover_issues(14.0, 16.0)[0][0] == qa.ERROR
    assert qa.cover_issues(18.0, 12.0)[0][0] == qa.ERROR          # under the 20 mm aggregate
    assert qa.cover_issues(25.0, 16.0, 40.0)[0][0] == qa.WARNING  # 40 - 10 = 30 needed


def test_spacing_with_the_real_bar_size():
    assert qa.spacing_issue(100.0, 25.0) is None                    # 100 - 27.5 = 72.5
    assert qa.spacing_issue(50.0, 25.0) is not None                 # 50 - 27.5 = 22.5 < 25
    assert qa.min_clear_mm(32.0) == 32.0 and qa.min_clear_mm(10.0) == 25.0


def test_pitch_and_ratio_limits():
    assert qa.max_pitch_mm(u'slab', 200.0) == 400.0 and qa.max_pitch_mm(u'slab', 120.0) == 360.0
    assert qa.max_pitch_mm(u'beam', 600.0) is None
    assert qa.ratio_issue(u'column', 0.001) and qa.ratio_issue(u'column', 0.05) and not qa.ratio_issue(u'column', 0.02)
    assert qa.ratio_issue(u'slab', 0.001, 30.0) and not qa.ratio_issue(u'slab', 0.002, 30.0)


def test_vibrator_gap():
    assert qa.vibrator_issue(300.0, [60.0, 80.0]) is None
    assert qa.vibrator_issue(600.0, [80.0, 50.0, 50.0]) is not None
    assert [round(g) for g in qa.gaps_clear([0.0, 100.0], [20.0, 20.0])] == [78]


def test_segments_clash_and_congestion():
    d, cos, overlap, _at = qa.segment_distance((0, 0, 0), (1000, 0, 0), (500, -500, 30), (500, 500, 30))
    assert abs(d - 30.0) < 1e-6 and cos < 0.01
    assert qa.pair_issue(d, cos, overlap, 16.0, 16.0) is None             # crossing mats touch: 16 + 16 / 2
    assert qa.pair_issue(10.0, cos, overlap, 16.0, 16.0)[0] == qa.ERROR
    assert qa.pair_issue(8.0, cos, overlap, 20.0, 8.0, bend=True) is None    # a bar seated in a link's corner
    assert qa.pair_issue(0.0, cos, overlap, 20.0, 20.0, bend=True)[0] == qa.ERROR
    d, cos, overlap, _at = qa.segment_distance((0, 0, 0), (1000, 0, 0), (0, 40, 0), (1000, 40, 0))
    assert cos > 0.99 and overlap == 1000.0
    assert qa.pair_issue(d, cos, overlap, 20.0, 20.0)[0] == qa.WARNING    # 40 - 22 = 18 < 25
    d, cos, overlap, _at = qa.segment_distance((0, 0, 0), (1000, 0, 0), (2000, 40, 0), (3000, 40, 0))
    assert overlap == 0.0 and qa.pair_issue(d, cos, overlap, 20.0, 20.0) is None
