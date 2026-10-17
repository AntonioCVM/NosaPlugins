# -*- coding: utf-8 -*-
"""T9.21 NOSA typical details: which a drawing calls for, names, references."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import typical_details as td  # noqa: E402


def test_needed_by_case():
    assert td.needed(['floor'], [u'bottom_x', u'trimmer_bottom', u'diagonal_bottom', u'end_ubar']) == [u'S3', u'OP1']
    assert td.needed(['floor'], [u'top_x', u'bottom_x']) == [u'S1']
    assert td.needed(['wall'], [u'vertical', u'trimmer', u'opening_ubar']) == [u'W4', u'W1']
    assert td.needed(['wall'], [u'vertical', u'corner_ubar']) == [u'W1', u'W2']
    assert td.needed(['stairs'], [u'stair_landing']) == [u'ST1']
    assert td.needed(['column'], [u'vertical'], flags=[u'column_top']) == [u'C4']
    assert td.needed(['column'], [u'vertical', u'corbel_compression']) == [u'CB1']
    assert td.needed(['foundation'], [u'bottom_x', u'dowel'], piled=True) == [u'C1', u'PC1']
    assert td.needed(['beam'], [u'top', u'bottom', u'stirrup']) == []


def test_every_detail_cites_the_4th_edition_in_english():
    for key, title, md, sketch in td.DETAILS:
        assert md.startswith(u'SMDSC 4th ed. MD ') and title == title.upper()
        assert td.view_name(key).startswith(td.PREFIX + key + u' - ')
        texts = [d[2] for kind, d in sketch if kind == 'text']
        assert texts and all(t.isascii() for t in texts)


def test_opening_corner_bars_stay_outside_the_opening():
    x0, y0, x1, y1 = 600.0, 500.0, 1400.0, 1100.0
    sketch = td.by_key()[u'OP1'][2]
    corners = [d for kind, d in sketch if kind == 'poly' and len(d) == 2 and d[0][0] != d[1][0] and d[0][1] != d[1][1]]
    assert len(corners) == 4
    for (ax, ay), (bx, by) in corners:
        for t in [k / 20.0 for k in range(21)]:
            x, y = ax + t * (bx - ax), ay + t * (by - ay)
            assert not (x0 < x < x1 and y0 < y < y1)
        assert abs(abs(bx - ax) - abs(by - ay)) < 1e-6          # at 45 degrees


def test_no_practice_name_in_the_details():
    for key, title, md, sketch in td.DETAILS:
        assert u'NOSA' not in title and u'NOSA' not in td.view_name(key)
        assert all(u'NOSA' not in d[2] for kind, d in sketch if kind == 'text')


def test_free_edge_u_bar_back_at_the_edge():
    sketch = td.by_key()[u'S3'][2]
    u = [d for kind, d in sketch if kind == 'poly' and len(d) == 4][0]
    back_x = u[1][0]
    assert u[1][0] == u[2][0] and back_x > u[0][0] and back_x > u[3][0]   # its back on the free edge side, legs in
    assert back_x < 1600.0                                                  # inside the cover


def test_faces_drawn_only_where_the_member_ends():
    for key, title, md, sketch in td.DETAILS:
        assert not [k for k, _d in sketch if k == 'rect'], key
        assert [k for k, _d in sketch if k == 'edge'], key


def test_dots_and_library():
    assert td.dot_points((0.0, 0.0, 100.0, 3)) == [(0.0, 0.0), (50.0, 0.0), (100.0, 0.0)]
    assert td.dot_points((140.0, 400.0, 140.0, 2, 200.0)) == [(140.0, 400.0), (140.0, 600.0)]
    keys = [k for k, _t, _m, _s in td.DETAILS]
    for k in (u'W1', u'W2', u'S2', u'S4', u'S6', u'ST1', u'RW1', u'C4', u'B3', u'CB1'):
        assert k in keys
