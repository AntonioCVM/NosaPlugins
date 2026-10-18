# -*- coding: utf-8 -*-
"""
Detailing limits of meshes (Phase 10, T10.7): the EC2 (UK NA) minimum steel and maximum pitch of a slab, base or
wall from its thickness, and the lightest bar and pitch that meet them. Minimums only - never design: the window
shows them as limits and fills them only when asked, labelled as minimum. No Revit.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

SIZES = (10, 12, 16, 20, 25)
PITCH_STEP = 25.0
PRACTICAL_PITCH = 150.0          # a minimum mesh at a closer pitch than this takes the next bar size


def fctm(fck):
    """EC2 Table 3.1: mean tensile strength (MPa), up to C50/60."""
    return 0.30 * fck ** (2.0 / 3.0)


def bar_area(dia):
    return math.pi * dia * dia / 4.0


def slab_limits(h, cover=30.0, dia=12.0, fck=32.0, fyk=500.0):
    """
    A slab or base `h` mm thick: (As,min mm2/m per direction, main pitch max, secondary pitch max).
    EC2 9.3.1.1(1) / 9.2.1.1(1): As,min = 0.26 fctm/fyk b d >= 0.0013 b d; 9.3.1.1(3): 3h <= 400 main,
    3.5h <= 450 secondary.
    """
    d = h - cover - dia / 2.0
    as_min = max(0.26 * fctm(fck) / fyk, 0.0013) * 1000.0 * d
    return as_min, min(3.0 * h, 400.0), min(3.5 * h, 450.0)


def wall_limits(h):
    """
    A wall `h` mm thick: (vertical As,min mm2/m per face, horizontal mm2/m per face, vertical pitch max, horizontal
    pitch max). EC2 9.6.2(1): 0.002 Ac vertical in all, half each face; 9.6.3(1): horizontal the greater of 25 % of
    the vertical and 0.001 Ac; 9.6.2(3) 3h <= 400, 9.6.3(2) 400.
    """
    vertical = 0.002 * 1000.0 * h / 2.0
    horizontal = max(0.25 * vertical * 2.0, 0.001 * 1000.0 * h) / 2.0
    return vertical, horizontal, min(3.0 * h, 400.0), 400.0


def provided(dia, pitch):
    """mm2/m of `dia` bars at `pitch`."""
    return bar_area(dia) * 1000.0 / pitch if pitch > 0 else 0.0


def lightest(as_min, pitch_max, sizes=SIZES):
    """
    (bar size, pitch) meeting As,min within pitch_max: the smallest size that does so at a practical pitch
    (>= 150), its pitch rounded down to 25; else the size giving the widest pitch.
    """
    best = None
    for dia in sizes:
        pitch = min(pitch_max, math.floor(bar_area(dia) * 1000.0 / as_min / PITCH_STEP) * PITCH_STEP)
        if pitch < PITCH_STEP:
            continue
        if pitch >= PRACTICAL_PITCH:
            return dia, pitch
        if best is None or pitch > best[1]:
            best = (dia, pitch)
    return best


def check(dia, pitch, as_min, pitch_max):
    """[issue] of a mesh of `dia` at `pitch` against the limits; [] when it meets them."""
    out = []
    if provided(dia, pitch) < as_min - 0.5:
        out.append(u'{:.0f} mm2/m < As,min {:.0f}'.format(provided(dia, pitch), as_min))
    if pitch > pitch_max + 0.5:
        out.append(u'pitch {:.0f} > {:.0f}'.format(pitch, pitch_max))
    return out
