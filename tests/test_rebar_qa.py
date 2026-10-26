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


def test_joint_clash_says_how_to_resolve_it_once():
    text = qa.joint_advice(u'clash: centrelines 10 mm apart, bars 20 + 25 at (1, 2, 3)')
    assert u'crank the beam bar' in text and u'second layer' in text and u'smaller bars' in text
    assert qa.joint_advice(text) == text
    assert qa.joint_advice(u'congested: clear gap 20 mm') == u'congested: clear gap 20 mm'


def test_congestion_layers_and_tight_bars():
    two = [(-100, 540, 20), (0, 540, 20), (100, 540, 20), (-100, 500, 20), (100, 500, 20), (0, 60, 20)]
    assert qa.face_layers(two, 300.0) == {u'top': 2, u'bottom': 1}
    assert qa.congestion_issues(two, 300.0) == []
    three = two + [(0, 460, 20)]
    assert u'3 layers in the top face' in qa.congestion_issues(three, 300.0)[0][1]
    tight = [(-20, 60, 20), (20, 60, 20)]                         # 40 centres, 18 clear < 25
    assert u'closer than the minimum' in qa.congestion_issues(tight, 300.0)[0][1]


def test_column_bar_retention():
    corners = [(-160, -160), (160, -160), (160, 160), (-160, 160)]
    bars = [(x, y, 20) for x, y in corners] + [(0, -160, 20), (0, 160, 20)]
    assert qa.unrestrained_bars(bars, corners) == []                # middle bars 140 clear of a corner bar
    wide = [(x * 2, y, 20) for x, y in corners] + [(0, -160, 20)]
    assert qa.unrestrained_bars(wide, [(x * 2, y) for x, y in corners]) == [4]   # 300 clear: needs a tie


def test_joint_vibrator_and_buildability_grade():
    assert qa.joint_vibrator_issue(300.0, [-100, 0, 100], [25, 25, 25]) is not None
    assert qa.joint_vibrator_issue(300.0, [-110, 0, 110], [16, 16, 16]) is None
    assert qa.buildability([])[:2] == (100.0, u'A+')
    assert qa.buildability([qa.WARNING] * 3)[1] == u'A'
    assert qa.buildability([qa.ERROR])[1] == u'B'
    assert qa.buildability([qa.ERROR] * 3)[1] == u'C'


def test_lap_is_not_a_clash():
    d, cos, overlap, _at = qa.segment_distance((0, 0, 0), (3000, 0, 0), (2000, 0, 0), (6000, 0, 0))
    assert qa.is_lap(d, cos, overlap, 3000.0, 4000.0, 20.0, 20.0)          # 1000 mm lap on one line
    d, cos, overlap, _at = qa.segment_distance((0, 0, 0), (3000, 0, 0), (1000, 0, 0), (2000, 0, 0))
    assert not qa.is_lap(d, cos, overlap, 3000.0, 1000.0, 20.0, 20.0)      # one bar inside the other: a clash


def test_distribution_pitch_md_s1():
    rows = [('bx', u'bottom', 40.0, 12.0, 150.0), ('by', u'bottom', 52.0, 10.0, 350.0),
            ('tx', u'top', 260.0, 12.0, 200.0), ('ty', u'top', 248.0, 10.0, 200.0)]
    issues = qa.distribution_issues(rows, 300.0)
    assert [k for k, _i in issues] == ['by'] and u'MD S1' in issues[0][1]


def test_bars_in_contact_are_not_congested():
    assert qa.pair_issue(1.1 * 12.0 + 0.5, 1.0, 500.0, 12.0, 12.0) is None       # a hole U-bar beside its cut bar
    assert qa.pair_issue(25.0, 1.0, 500.0, 12.0, 12.0)[0] == qa.WARNING           # a 12 mm gap is congestion


class _Id(object):
    def __init__(self, v):
        self.IntegerValue = v


class _Bar(object):
    def __init__(self, v):
        self.Id = _Id(v)


def _gid(eid):
    return eid.IntegerValue


def _random_samples(rng, sets=12, bars=6):
    """Bar sets crossing, running side by side, lapping and bending, packed in a 1 m cube."""
    samples = []
    for s in range(sets):
        bar = _Bar(1000 + s)
        dia = rng.choice((10.0, 12.0, 16.0, 20.0, 25.0))
        axis = rng.randrange(3)
        for k in range(bars):
            a = [rng.uniform(0, 1000) for _ in range(3)]
            b = list(a)
            b[axis] += rng.uniform(100, 900)
            chain = [(tuple(a), tuple(b), False)]
            if rng.random() < 0.3:                        # a leg after a bend
                c = list(b)
                c[(axis + 1) % 3] += rng.uniform(50, 300)
                chain.append((tuple(b), tuple(c), True))
            if rng.random() < 0.2 and samples:            # a bar lapped on another set's bar
                other = samples[rng.randrange(len(samples))][2][0]
                chain = [(other[0], tuple(p + 40.0 * (i == axis) for i, p in enumerate(other[1])), False)]
            samples.append((bar, dia, chain, u'{:02d}'.format(s)))
    return samples


def _key(findings):
    return [(f.Mark, f.Check, f.Severity, f.Issue, f.ElementId.IntegerValue) for f in findings]


def test_pairs_sweep_gives_what_the_double_loop_gave():
    import random
    rng = random.Random(2026)
    for trial in range(60):
        samples = _random_samples(rng, sets=rng.randrange(2, 14), bars=rng.randrange(1, 8))
        owner = None
        if trial % 2:                                      # a joint: only bars of different members count
            owner = dict((1000 + s, s % 3) for s in range(20))
        new = qa._pairs(samples, u'X', 20.0, _gid, owner)
        old = qa._pairs_reference(samples, u'X', 20.0, _gid, owner)
        assert _key(new) == _key(old), trial


def test_pairs_sweep_finds_a_clash_and_skips_far_bars():
    a = (_Bar(1), 16.0, [((0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), False)], u'01')
    b = (_Bar(2), 16.0, [((500.0, -500.0, 0.0), (500.0, 500.0, 0.0), False)], u'02')
    far = (_Bar(3), 16.0, [((0.0, 5000.0, 0.0), (1000.0, 5000.0, 0.0), False)], u'03')
    found = qa._pairs([a, b, far], u'X', 20.0, _gid)
    assert len(found) == 1 and found[0].Severity == qa.ERROR and found[0].Mark == u'01 / 02'
    assert qa.candidate_pairs(qa._segments([a, far], _gid), 75.0) == []


def test_candidate_pairs_are_exactly_the_double_loop_box_test():
    import random
    rng = random.Random(7)
    for trial in range(40):
        segs = qa._segments(_random_samples(rng, sets=rng.randrange(2, 12), bars=rng.randrange(1, 7)), _gid)
        owner = dict((1000 + s, s % 2) for s in range(20)) if trial % 2 else None
        reach = 75.0
        brute = [(i, j) for i in range(len(segs)) for j in range(i + 1, len(segs))
                 if segs[i][0] != segs[j][0] and not (owner is not None and owner.get(segs[i][0]) == owner.get(segs[j][0]))
                 and not any(segs[i][5][k] - reach > segs[j][6][k] or segs[j][5][k] - reach > segs[i][6][k]
                             for k in range(3))]
        assert qa.candidate_pairs(segs, reach, owner) == brute, trial


def test_link_zones_of_b1_b2_in_their_spans_and_the_regression_caught():
    # B1-B2 (6000 mm between column centres, columns 450 wide): after 947c985 the zones are 12@100 275..1375,
    # 16@200 1500..4500, 12@100 4625..5725; 6d58a08 had turned them round (12 at -825..275, 16 at -1500..1500)
    from nosa_utils import rebar_qa as q
    supports = [(-225.0, 225.0), (5775.0, 6225.0)]
    zones = [[275.0 + 100.0 * k for k in range(12)], [1500.0 + 200.0 * k for k in range(16)],
             [4625.0 + 100.0 * k for k in range(12)]]
    assert all(q.link_zone_issues(z, supports) == [] for z in zones)
    turned = [[-825.0 + 100.0 * k for k in range(12)], [-1500.0 + 200.0 * k for k in range(16)]]
    first, middle = [q.link_zone_issues(z, supports) for z in turned]
    assert any(u'inside a support' in i for i in first) and any(u'across 1 support' in i for i in first)
    assert any(u'inside a support' in i for i in middle) and any(u'across 1 support' in i for i in middle)


def test_link_zone_touching_a_support_face_is_not_inside_it():
    from nosa_utils import rebar_qa as q
    assert q.link_zone_issues([225.0, 325.0], [(-225.0, 225.0)]) == []
    assert q.link_zone_issues([], [(-225.0, 225.0)]) == []
