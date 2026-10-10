# -*- coding: utf-8 -*-
"""Continuous nibs (SMDSC MN1/MN2) and half joints (SMDSC 6.9, EC2 Annex J) — no Revit."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib')))
from nosa_utils import nibs  # noqa: E402


def test_mode_by_depth():
    assert nibs.nib_mode(250.0, 40.0, 10.0)[0] == 'MN1'
    mode, notes = nibs.nib_mode(150.0, 40.0, 10.0)
    assert mode == 'MN2' and not notes
    mode, notes = nibs.nib_mode(120.0, 25.0, 8.0)
    assert notes and u'140' in notes[0]


def test_pitches():
    assert nibs.nib_pitch_mm(250.0) == 400.0 and nibs.nib_pitch_mm(100.0) == 300.0
    assert nibs.nib_pitch_mm(250.0, concentrated=True) == 250.0
    assert nibs.secondary_pitch_mm(250.0) == 450.0


def test_mn1_link_spans_web_and_nib():
    pts = nibs.mn1_link(300.0, 150.0, 250.0, 40.0, 10.0)
    assert pts[0] == (-105.0, 45.0) and pts[2] == (255.0, 205.0)
    bars = nibs.nib_bar_positions(300.0, 150.0, 250.0, 40.0, 10.0, 12.0)
    assert all(y > 150.0 for y, _z in bars) and len(bars) == 2       # a 150 nib: the outer corners only


def test_mn2_ubar_and_lacer():
    pts, short = nibs.mn2_ubar(300.0, 150.0, 150.0, 40.0, 10.0, 400.0, 1000.0)
    assert pts[1][1] == pts[2][1] == 255.0                 # loop at the nib face less cover
    assert pts[0][1] == -105.0 and short == 145.0          # the legs reach the far side, 145 short
    assert abs(pts[2][0] - pts[1][0]) == 70.0
    y, z = nibs.mn2_lacer(300.0, 150.0, 150.0, 40.0, 10.0)
    assert 150.0 < y < 255.0 and z == 75.0


def test_half_joint_layout():
    hj = nibs.half_joint(300.0, 300.0, 600.0, 300.0, 40.0, 10.0, 12.0, 450.0)
    assert hj['hangers'][0] == 345.0 and len(hj['hangers']) == 4
    assert len(hj['ubars']) == 2
    u = hj['ubars'][0]
    assert u[0][0] == hj['hangers'][-1] + 450.0 and u[1][0] == 46.0
    assert u[0][2] == 300.0 + 40.0 + 10.0 + 6.0
    assert hj['nib_links'] and hj['nib_links'][-1] <= 300.0 - 45.0
    assert hj['bottom_stop_mm'] == 340.0
