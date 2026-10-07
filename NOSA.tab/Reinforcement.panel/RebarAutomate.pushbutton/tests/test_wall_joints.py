# -*- coding: utf-8 -*-
"""wall_joints (T8.40, SMDSC MW2): corners and T junctions between selected walls."""
from __future__ import print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
import wall_joints as wj


def _w(i, p0, p1, t=225.0):
    return {'id': i, 'p0': p0, 'p1': p1, 'thickness_mm': t}


def test_l_corner_one_through_one_stop():
    out = wj.classify([_w(1, (0, 0), (4000, 0)), _w(2, (4000, 0), (4000, 3000), 300.0)])
    assert out[1][0]['mode'] == wj.FREE and out[1][1]['mode'] == wj.THROUGH
    assert out[1][1]['other_half_mm'] == 150.0
    assert out[2][0]['mode'] == wj.STOP and out[2][0]['other_half_mm'] == 112.5 and out[2][1]['mode'] == wj.FREE
    print(u'[PASS] test_l_corner_one_through_one_stop')


def test_t_junction_and_parallel_walls():
    out = wj.classify([_w(5, (0, 0), (6000, 0)), _w(3, (3000, 0), (3000, 2500))])
    assert out[5] == ({'mode': wj.FREE, 'other_half_mm': 0.0, 'other_id': None},) * 2
    assert out[3][0]['mode'] == wj.STOP and out[3][0]['other_id'] == 5     # abuts the long wall
    out = wj.classify([_w(1, (0, 0), (4000, 0)), _w(2, (4000, 0), (8000, 0))])
    assert out[1][1]['mode'] == wj.FREE and out[2][0]['mode'] == wj.FREE   # in line: not a corner
    print(u'[PASS] test_t_junction_and_parallel_walls')


if __name__ == '__main__':
    test_l_corner_one_through_one_stop()
    test_t_junction_and_parallel_walls()
