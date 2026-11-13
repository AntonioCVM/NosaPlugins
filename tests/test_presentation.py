# -*- coding: utf-8 -*-
"""SMDSC 6.2.2 bar presentation rules (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import presentation as pr  # noqa: E402


def _set(id_, mark, x0, n, spacing, y0=0.0, y1=3000.0, count=None):
    # bars along y, spread along x
    return {'id': id_, 'mark': mark, 'count': count or n, 'bar_dir': (0.0, 1.0), 'spread_dir': (1.0, 0.0),
            'first': (x0, (y0 + y1) / 2.0), 'last': (x0 + (n - 1) * spacing, (y0 + y1) / 2.0),
            'ends': ((x0, y0), (x0, y1)), 'spacing': spacing}


def test_typical_bar():
    assert pr.is_typical_bar_set(0.0, True)
    assert not pr.is_typical_bar_set(1.0, True)          # bars cut by a section
    assert not pr.is_typical_bar_set(0.0, False)         # seen end-on


def test_zone_quantities():
    sets = [_set(1, u'63', 0, 12, 150), _set(2, u'63', 4000, 8, 150), _set(3, u'64', 0, 5, 200)]
    assert pr.zone_labels(sets) == {1: u'(12)', 2: u'(8)'}


def test_alternate_and_stagger():
    a, b = _set(1, u'63', 0, 10, 300), _set(2, u'64', 150, 10, 300)
    assert pr.relation(a, b) == u'ALT'
    assert pr.relation(a, _set(3, u'64', 100, 10, 300)) is None          # not half a pitch apart
    c = _set(4, u'63', 150, 10, 300, y0=800.0, y1=3800.0)
    assert pr.relation(a, c) == u'STG'
    d = _set(5, u'63', 0, 10, 300, y0=3000.0, y1=6000.0)
    assert pr.relation(a, d) is None                                      # end to end, two runs
    assert pr.relations([a, b, c]) == [(1, 2, u'ALT'), (1, 4, u'STG')]


def test_curtailed_ends_and_ticks():
    assert pr.curtailed(2000.0, 0.0, 6000.0, 40.0, 16.0)
    assert not pr.curtailed(50.0, 0.0, 6000.0, 40.0, 16.0)
    p, q = pr.tick((100.0, 0.0), (1.0, 0.0), (0.0, 1.0), 50)
    assert p == (100.0, 0.0)
    assert abs(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) - 30.0) < 1e-6
    assert abs(math.hypot(q[0] - p[0], q[1] - p[1]) - 150.0) < 1e-6


def test_see_drawing():
    assert pr.see_drawing(u'4002', u'4003') == u'SEE DRG 4002'
    assert pr.see_drawing(u'4002', u'4002') is None
    assert pr.see_drawing(u'', u'4002') is None


def test_layer_slots_spread_coincident_sets():
    a = dict(_set(1, u'01', 0, 20, 150), layer=u'B1')
    b = dict(_set(2, u'02', 75, 20, 150), layer=u'T1')
    c = dict(_set(3, u'03', 9000, 5, 150), layer=u'B1')            # its own zone
    slots = pr.layer_slots([b, a, c])
    assert slots[1] == 1.0 / 3.0 and slots[2] == 2.0 / 3.0 and slots[3] == 0.5


def test_face_of_a_bar():
    assert pr.face(180.0, 0.0, 250.0) == u'top' and pr.face(40.0, 0.0, 250.0) == u'bottom'


def test_link_zone_texts():
    assert pr.zone_quantity(17, 194.5) in (u'(17@194)', u'(17@195)')
    assert pr.zone_quantity(13, 100.0) == u'(13@100)'
    assert pr.total_callout(u'26H8-06', 43, u'LINKS') == u'43H8-06 LINKS'
    assert pr.total_callout(u'20H16-01 B1', 39) == u'39H16-01 B1'


def test_bar_notes():
    assert pr.bar_note(u'00') == u'' and pr.bar_note(u'11') == u'L-BARS' and pr.bar_note(u'21') == u'U-BARS'
    assert pr.bar_note(u'51') == u'LINKS' and pr.bar_note(u'52', in_twos=True) == u'LINKS IN 2s'


def test_spacer_bars_are_called_spacers_whatever_their_shape():
    assert pr.bar_note(u"00", layer=u"spacer") == u'SPACERS'
    assert pr.bar_note(u"00", layer=u"top") == u''
    assert pr.bar_note(u"21", layer=u"bottom") == u'U-BARS'


def test_curtailment_dims_from_support_faces_and_laps():
    supports = [(-225.0, 225.0), (5775.0, 6225.0)]
    bars = [(-200.0, 1500.0, u'top'), (4500.0, 6200.0, u'top'), (-200.0, 6200.0, u'bottom')]
    dims = pr.curtailment_dims(bars, supports)
    assert ('cut', 225.0, 1500.0, u'top') in dims and ('cut', 4500.0, 5775.0, u'top') in dims
    assert not [d for d in dims if d[3] == u'bottom']             # anchored in both supports
    laps = pr.curtailment_dims([(0.0, 4000.0, u'bottom'), (3200.0, 8000.0, u'bottom')], [(-225.0, 225.0)])
    assert ('lap', 3200.0, 4000.0, u'bottom') in laps


def test_single_bars_group_by_place():
    ring = [(i, '01', (math.cos(a) * 180, math.sin(a) * 180, 0.0), (math.cos(a) * 180, math.sin(a) * 180, 3000.0))
            for i, a in enumerate(k * math.pi / 4 for k in range(8))]
    groups = pr.single_clusters(ring)
    assert set(g[1] for g in groups.values()) == {8}           # the eight bars of a round column: one group
    trimmers = [(1, '01', (0, 0, 0), (0, 0, 2000)), (2, '01', (60, 0, 0), (60, 0, 2000)),
                (3, '01', (1500, 0, 0), (1500, 0, 2000)), (4, '01', (0, 0, 2500), (2000, 0, 2500))]
    groups = pr.single_clusters(trimmers)
    assert groups[1] == groups[2] and groups[1][1] == 2           # a pair each side of the opening
    assert groups[3][1] == 1 and groups[4][1] == 1                # the far side and the cross bar on their own
    other_mark = [(1, '01', (0, 0, 0), (0, 0, 2000)), (2, '02', (60, 0, 0), (60, 0, 2000))]
    assert pr.single_clusters(other_mark)[1][1] == 1


def test_end_arrow_points_at_the_end_from_beside_the_bar():
    tip, centre, box = pr.end_arrow((1000.0, 0.0), (1.0, 0.0), (0.0, 1.0), 100.0, 60.0, 50, 75.0)
    assert tip == (1000.0, 105.0)                                  # beside the bar, level with its end
    assert centre[0] < tip[0] - 50 * pr.ARROW_PAPER_MM and centre[1] == tip[1]   # the mark at the tail
    _tip, _c, box2 = pr.end_arrow((1000.0, 0.0), (1.0, 0.0), (0.0, 1.0), 100.0, 60.0, 50, 75.0, row=1)
    assert box2[1] >= box[3] - 1e-6                                 # a second row clear of the first


def test_indicator_line_crosses_off_the_other_typical_bar():
    for slot in (0.5, 0.3, 0.7, 0.1, 0.9):
        f = pr.junction_fraction(slot)
        assert 0.0 < f < 1.0 and abs(f - slot) >= 0.25 - 1e-9


def test_support_chain_and_arc_stations():
    xs, labels = pr.support_chain([(0.0, 300.0), (5000.0, 5300.0), (9000.0, 9400.0)])
    assert xs == [0.0, 300.0, 5000.0, 5300.0, 9000.0, 9400.0]
    assert labels == [u'SUPPORT', u'', u'SUPPORT', u'', u'SUPPORT']
    assert pr.support_chain([]) == ([], [])
    assert pr.arc_stations(6000.0) == [0.0, 1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0]
    assert pr.arc_stations(1100.0) == [0.0, 500.0, 1100.0]
    assert pr.chainage_text(2000.0) == u'CH 2000'


def test_column_ratio_and_confinement():
    text = pr.steel_ratio_text([(8, 20.0)], 400.0 * 400.0)
    assert text.startswith(u'ρ = 1.57 %') and u'8H20' in text and u'2513' in text
    assert u'UNDER 0.2 %' in pr.steel_ratio_text([(4, 12.0)], 600.0 * 600.0)
    assert u'OVER 4 %' in pr.steel_ratio_text([(12, 32.0)], 300.0 * 300.0)
    assert pr.confinement_zones([(0, 600, 100), (600, 2400, 200), (2400, 3000, 100)]) == [(0, 600), (2400, 3000)]
    assert pr.confinement_zones([(0, 3000, 200)]) == []
    assert pr.confinement_zones([(0, 30, 100), (30, 2400, 200), (2400, 3000, 100)]) == [(2400, 3000)]


def test_clearest_between_bars():
    xs = [0.0, 50.0, 100.0, 150.0, 200.0]
    assert pr.clearest(xs, [0.0, 100.0, 200.0]) in (1, 3)
    assert pr.clearest(xs, []) == 2 and pr.clearest([], [1.0]) is None


def test_links_chain_takes_the_supports_in():
    xs, labels = pr.links_chain([(50.0, 1250.0), (1375.0, 4175.0)], [(-450.0, 0.0), (4225.0, 4675.0)])
    assert xs == [-450.0, 0.0, 50.0, 1250.0, 1375.0, 4175.0, 4225.0, 4675.0]
    assert labels[0] == pr.SUPPORT_TEXT and labels[-1] == pr.SUPPORT_TEXT and labels[1] == u''
    assert pr.links_chain([], [(0.0, 450.0)]) == ([0.0, 450.0], [pr.SUPPORT_TEXT])


def test_pile_table_and_starter_chain():
    rows = pr.pile_table([(37450.0, 39450.0, 600.0, -825.0), (38550.0, 40550.0, 600.0, -825.0),
                          (37450.0, 40550.0, 600.0, -825.0), (38550.0, 39450.0, 600.0, -825.0)], (38000.0, 40000.0))
    assert [r[0] for r in rows] == [u'P1', u'P2', u'P3', u'P4']
    assert rows[0][2] == [u'P1', u'-550', u'550', u'600', u'-0.825']          # top left first
    assert rows[3][2][1:3] == [u'550', u'-550']
    pts, labels = pr.starter_chain(-900.0, -825.0, 0.0, 1200.0)
    assert pts == [-900.0, -825.0, 0.0, 1200.0] and labels == [u'', u'', pr.PROJECTION_TEXT]
    pts, labels = pr.starter_chain(-900.0, -818.0, 0.0, 1200.0, mat=-825.0)
    assert pts == [-900.0, -825.0, 0.0, 1200.0] and labels[0] == pr.COVER_TEXT
    assert pr.starter_chain(-900.0, -825.0, 0.0, -10.0) == ([], [])


def test_curved_beam_section_between_stations():
    stations = pr.arc_stations(6955.0)
    assert stations[:3] == [0.0, 1000.0, 2000.0]
    t = pr.between_stations(0.12, stations, 6955.0)         # 835 mm: between CH 0 and CH 1000
    assert abs(t * 6955.0 - 500.0) < 1e-6
    t = pr.between_stations(0.5, stations, 6955.0)
    assert abs(t * 6955.0 - 3500.0) < 1e-6
