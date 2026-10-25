# -*- coding: utf-8 -*-
"""sloped (T8.58): bars of a sloping slab lifted onto its faces."""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import sloped  # noqa: E402

SLOPE = 0.1                                       # 10 % rising along x
N = (-SLOPE / math.sqrt(1 + SLOPE ** 2), 0.0, 1.0 / math.sqrt(1 + SLOPE ** 2))
TOP = ((0.0, 0.0, 300.0), N)                      # top face, outward normal up
BOTTOM = ((0.0, 0.0, 0.0), (-N[0], 0.0, -N[2]))   # bottom face, outward normal down


def test_level_faces_are_left_alone():
    assert not sloped.tilted(((0, 0, 0), (0.0, 0.0, -1.0)))
    assert sloped.tilted(BOTTOM)


def test_bottom_bar_keeps_its_cover_square_to_the_face():
    x, y, z = sloped.lift((2000.0, 500.0, 48.0), BOTTOM, TOP)        # 40 cover + 8 half bar, worked out flat
    assert abs(z - (200.0 + 48.0 * math.sqrt(1 + SLOPE ** 2))) < 1e-6
    # its distance square to the bottom face is still 48
    d = (z - SLOPE * x) / math.sqrt(1 + SLOPE ** 2)
    assert abs(d - 48.0) < 1e-6


def test_top_bar_follows_the_top_face():
    x, y, z = sloped.lift((3000.0, 0.0, 252.0), BOTTOM, TOP)          # 48 under the top
    assert abs(z - (300.0 + 300.0 - 48.0 * math.sqrt(1 + SLOPE ** 2))) < 1e-6


def test_set_direction_square_to_the_bars_on_the_face():
    bar = (1.0 / math.sqrt(1 + SLOPE ** 2), 0.0, SLOPE / math.sqrt(1 + SLOPE ** 2))   # a bar up the slope
    d, k = sloped.set_direction((0.0, 1.0, 0.0), bar, TOP)            # spread across the slope: unchanged
    assert abs(d[1] - 1.0) < 1e-9 and abs(k - 1.0) < 1e-9
    d, k = sloped.set_direction((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), TOP)   # bars across, spread up the slope
    assert abs(k - math.sqrt(1 + SLOPE ** 2)) < 1e-9 and abs(d[2] / d[0] - SLOPE) < 1e-9
