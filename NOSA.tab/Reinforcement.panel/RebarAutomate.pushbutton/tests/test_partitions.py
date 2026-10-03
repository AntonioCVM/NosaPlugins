# -*- coding: utf-8 -*-
"""T7.1 partitions: naming, grouping of identical hosts, BBS No. of mbrs (no Revit)."""
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys

_ext = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext not in sys.path:
    sys.path.insert(0, _ext)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from rebar_partitions import bar_signature, fingerprint, plan, prefix_for  # noqa: E402
from rebar_schedule import bbs_rows  # noqa: E402
from rebar_export_bvbs import bvbs_record  # noqa: E402

_COLUMN_BARS = [bar_signature(u'vertical', u'00', u'A=3000', 20, 4, 3000.0),
                bar_signature(u'link', u'51', u'A=300;B=300', 10, 12, 1400.0)]


def _host(hid, category=u'OST_StructuralColumns', mark=u'', elevation=0.0, x=0.0, y=0.0, bars=None):
    return {'id': hid, 'category': category, 'mark': mark, 'elevation_mm': elevation,
            'x_mm': x, 'y_mm': y,
            'fingerprint': fingerprint(category, u'300x300', bars or _COLUMN_BARS)}


def test_prefixes():
    assert prefix_for(u'OST_StructuralColumns') == u'C'
    assert prefix_for(u'OST_StructuralFraming') == u'B'
    assert prefix_for(u'OST_StructuralFoundation') == u'F'
    assert prefix_for(u'OST_Floors') == u'S'
    assert prefix_for(u'OST_Walls') == u'W'
    assert prefix_for(u'') == u'M'


def test_signature_ignores_small_length_noise_and_bar_order():
    a = fingerprint(u'C', u'T', [bar_signature(u'v', u'00', u'', 20, 4, 3000.0),
                                  bar_signature(u'l', u'51', u'', 10, 12, 1400.0)])
    b = fingerprint(u'C', u'T', [bar_signature(u'l', u'51', u'', 10, 12, 1401.0),
                                  bar_signature(u'v', u'00', u'', 20, 4, 3000.0)])
    assert a == b
    c = fingerprint(u'C', u'T', [bar_signature(u'v', u'00', u'', 20, 4, 3100.0),
                                  bar_signature(u'l', u'51', u'', 10, 12, 1400.0)])
    assert a != c


def test_identical_hosts_share_a_partition_counted_once():
    hosts = [_host(1, x=0.0), _host(2, x=5000.0), _host(3, x=10000.0),
             _host(4, x=15000.0, bars=_COLUMN_BARS[:1])]
    result = plan(hosts)
    assert result[1] == {'partition': u'C1', 'group': 1, 'representative': True, 'members': 3}
    assert result[2]['partition'] == u'C1' and not result[2]['representative']
    assert result[2]['members'] == 1
    assert result[4]['partition'] == u'C2' and result[4]['members'] == 1


def test_without_grouping_every_host_is_its_own_member():
    result = plan([_host(1), _host(2, x=5000.0)], group_identical=False)
    assert [result[1]['partition'], result[2]['partition']] == [u'C1', u'C2']
    assert all(r['representative'] and r['members'] == 1 for r in result.values())


def test_host_mark_names_the_partition_and_is_never_reused():
    hosts = [_host(1, mark=u'C1', bars=_COLUMN_BARS[:1]), _host(2, x=5000.0)]
    result = plan(hosts)
    assert result[1]['partition'] == u'C1'
    assert result[2]['partition'] == u'C2'


def test_identical_marked_hosts_list_their_marks():
    result = plan([_host(1, mark=u'C10'), _host(2, mark=u'C2', x=5000.0)])
    assert result[1]['partition'] == u'C2, C10'
    many = plan([_host(i, mark=u'C{}'.format(i), x=i * 1000.0) for i in range(1, 6)])
    assert many[1]['partition'] == u'C1 to C5'


def test_numbering_by_level_then_plan_rows_then_left_to_right():
    hosts = [_host(1, elevation=3000.0, bars=[bar_signature(u'a', u'', u'', 1, 1, 1)]),
             _host(2, y=0.0, x=9000.0, bars=[bar_signature(u'b', u'', u'', 1, 1, 1)]),
             _host(3, y=6000.0, x=9000.0, bars=[bar_signature(u'c', u'', u'', 1, 1, 1)]),
             _host(4, y=6000.0, x=0.0, bars=[bar_signature(u'd', u'', u'', 1, 1, 1)]),
             _host(5, category=u'OST_StructuralFraming')]
    result = plan(hosts)
    assert [result[i]['partition'] for i in (4, 3, 2, 1)] == [u'C1', u'C2', u'C3', u'C4']
    assert result[5]['partition'] == u'B1'


def test_bbs_row_multiplies_by_members():
    row = bbs_rows([{'member': u'C1', 'mark': u'01', 'diameter_mm': 20, 'count': 4, 'members': 3,
                     'unit_length_mm': 3000.0, 'shape_code': u'00', 'shape_params': u'A=3000'}])[0]
    assert row[:6] == [u'C1', u'01', u'H20', u'3', u'4', u'12']


def test_bvbs_piece_count_includes_members():
    record = bvbs_record({'mark': u'01', 'diameter_mm': 20, 'count': 4, 'members': 3,
                          'unit_length_mm': 3000.0})
    assert u'@n12@' in record
