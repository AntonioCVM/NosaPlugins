# -*- coding: utf-8 -*-
"""nosa_utils.loop_fit - closed links fitted to the box asked (Revit re-fits them half a bar short, 2026-10-26)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import loop_fit as lf  # noqa: E402


def _revit(box):
    """What Revit gave for a box in the live probe: 5 mm short on the right and top, 5 mm in on the left."""
    return (box[0] + 5.0, box[1] - 5.0, box[2], box[3] - 5.0)


def test_the_box_converges_to_the_asked_lines_in_a_few_tries():
    want = (-180.0, 180.0, -180.0, 180.0)                 # a 360 x 360 column link
    box, got = want, _revit(want)
    tries = 1
    while lf.off_by(want, got) > 0.05 and tries < lf.TRIES:
        box = lf.next_box(want, box, got)
        got = _revit(box)
        tries += 1
    assert lf.off_by(want, got) <= 0.05 and tries <= 3


def test_a_loop_already_right_is_left_alone():
    want = (0.0, 212.0, 0.0, 468.0)
    assert lf.off_by(want, want) == 0.0
    assert lf.next_box(want, want, want) == want
