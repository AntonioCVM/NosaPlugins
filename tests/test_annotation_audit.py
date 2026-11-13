# -*- coding: utf-8 -*-
"""Drawing annotation audit: overlaps, crossings, frame, bands (no Revit)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import annotation_audit as aa  # noqa: E402


def test_overlap_and_touch():
    assert aa.area_overlap((0, 0, 10, 5), (9, 4, 20, 8))
    assert not aa.area_overlap((0, 0, 10, 5), (10, 0, 20, 5))          # side by side
    assert not aa.area_overlap((0, 0, 10, 5), (9.9, 0, 20, 5), tol=0.2)
    assert aa.overlapping_pairs({'a': (0, 0, 10, 5), 'b': (5, 1, 8, 3), 'c': (30, 0, 40, 5)}) == [('a', 'b')]
    assert aa.overlapping_pairs({'a': (0, 0, 10, 5), 'b': (5, 1, 8, 3)}, same=lambda x, y: True) == []


def test_centred_box():
    # a tag's box run on to the right as far as its bar: only the text, centred on the head, is kept
    assert aa.centred_box((10.0, 5.0), (0.0, 3.0, 100.0, 7.0)) == (0.0, 3.0, 20.0, 7.0)
    assert aa.centred_box((90.0, 5.0), (0.0, 4.0, 100.0, 6.5)) == (80.0, 4.0, 100.0, 6.0)


def test_crossings():
    assert aa.cross(((0, 0), (10, 10)), ((0, 10), (10, 0)))
    assert not aa.cross(((0, 0), (10, 0)), ((10, 0), (10, 10)))         # a jog: lines meeting at a corner
    assert not aa.cross(((0, 0), (10, 0)), ((5, 1), (5, 10)))           # a T short of the line
    assert not aa.cross(((0, 0), (10, 0)), ((2, 0), (8, 0)))            # running together
    segs = {'u1': ((0, 0), (10, 0)), 'u2': ((5, -5), (5, 5)), 'u3': ((20, 0), (30, 0))}
    assert aa.crossing_pairs(segs) == [('u1', 'u2')]


def test_segment_through_box():
    box = (0, 0, 10, 4)
    assert aa.segment_hits_box(((-5, 2), (15, 2)), box)
    assert not aa.segment_hits_box(((-5, -1), (15, -1)), box)          # an underline just under its text
    assert not aa.segment_hits_box(((-5, 0), (15, 0)), (0, 0.5, 10, 4))
    assert aa.segment_hits_box(((5, 2), (5, 2.5)), box)                 # inside


def test_frame_and_bands():
    frame = (0, 0, 100, 100)
    assert not aa.outside((10, 10, 20, 15), frame)
    assert aa.outside((95, 10, 105, 15), frame)
    member = (30, 30, 70, 70)
    labels = {'l1': (5, 50, 25, 54), 'l2': (5.0, 40, 25.2, 44), 'r1': (75, 50, 90, 54), 'over': (40, 40, 50, 44)}
    got = dict((b['side'], b) for b in aa.bands(labels, member))
    assert set(got) == set(['left', 'right'])
    assert sorted(got['left']['keys']) == ['l1', 'l2'] and abs(got['left']['spread'] - 0.2) < 1e-9
    assert abs(got['left']['off'] - 4.9) < 1e-9 and abs(got['right']['off'] - 5.0) < 1e-9
    assert aa.side_of((40, 40, 50, 44), member) is None


def test_callout_lines():
    labels = [(0.0, 10.0, 20.0, 13.0)]
    lines = {'under': ((0.0, 9.5), (25.0, 9.5)), 'jog': ((25.0, 9.5), (25.0, 2.0)), 'run': ((25.0, 2.0), (40.0, 2.0)),
             'strip': ((0.0, 30.0), (50.0, 30.0)), 'far': ((60.0, 9.5), (70.0, 9.5))}
    assert aa.callout_lines(lines, labels) == set(['under', 'jog', 'run'])


if __name__ == '__main__':
    test_overlap_and_touch()
    test_centred_box()
    test_crossings()
    test_segment_through_box()
    test_frame_and_bands()
    test_callout_lines()
    print('test_annotation_audit: OK')
