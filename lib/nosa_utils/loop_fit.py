# -*- coding: utf-8 -*-
"""
nosa_utils.loop_fit - a closed link fitted to the box it was asked for (2026-10-26). Revit re-fits a closed loop to
its catalogue shape and makes it half a bar smaller on two sides (a 360 x 360 column link came out 355 x 355, its
corner bars 8.6 mm into the bend); RebarShapeDrivenAccessor.ScaleToBox takes its box from another reference, so
the box is corrected by what each side missed and tried again until the loop sits on the asked lines. No Revit.
Extents are (u0, u1, v0, v1) along the loop's two in-plane axes.
"""

TRIES = 4


def next_box(want, box, got):
    """The box for the next ScaleToBox: the last one moved out (or in) by what each side of the result missed."""
    return (box[0] - (got[0] - want[0]), box[1] + (want[1] - got[1]),
            box[2] - (got[2] - want[2]), box[3] + (want[3] - got[3]))


def off_by(want, got):
    """The largest miss of any side (same units)."""
    return max(abs(g - w) for g, w in zip(got, want))
