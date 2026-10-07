# -*- coding: utf-8 -*-
"""
nosa_utils.links — links (stirrups, ties) to IStructE SMDSC 6.3 / EC2 9.2.2 + UK NA. Pure Python.

Shared by every element that has links: the minimum shear ratio and preferred link size hold for
any of them; the beam rules (pitch, legs across the width, side bars, open links) are below, and
the column rules of SMDSC 6.4 join them with T8.38.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

FYK_MPA = 500.0
MIN_LINK_DIA_MM = 8.0            # SMDSC 6.3: preferred minimum
MAX_PITCH_MM = 300.0
MAX_LATERAL_LEG_MM = 600.0
MAX_BAR_TO_LEG_MM = 150.0        # no bar further than this from a vertical leg
OPEN_LINK_WIDTH_MM = 450.0       # open links (with a locking link) from this rib width
SIDE_BARS_DEPTH_MM = 1000.0      # side bars H16 at <= 250 from this depth
SIDE_BAR_DIA_MM = 16.0
SIDE_BAR_PITCH_MM = 250.0


def rho_w_min(fck_mpa, fyk_mpa=FYK_MPA):
    """EC2 9.2.2(5) with the UK NA: 0.08 sqrt(fck) / fyk (0.085 % for C30/37 in SMDSC 6.3)."""
    return 0.08 * math.sqrt(fck_mpa) / fyk_mpa


def link_ratio(legs, link_dia_mm, spacing_mm, width_mm):
    """Asw / (s bw) of links with `legs` vertical legs."""
    return legs * math.pi * link_dia_mm ** 2 / 4.0 / (spacing_mm * width_mm)


def effective_depth_mm(height_mm, cover_mm, link_dia_mm, bar_dia_mm):
    return height_mm - cover_mm - link_dia_mm - bar_dia_mm / 2.0


def pitch_limits_mm(d_mm, legs=2, compression_bar_dia_mm=None):
    """(minimum, maximum) link pitch: max(100, 50 + 12.5 legs) and min(300, 0.75 d, 12 phi')."""
    least = max(100.0, 50.0 + 12.5 * legs)
    most = min(MAX_PITCH_MM, 0.75 * d_mm)
    if compression_bar_dia_mm:
        most = min(most, 12.0 * compression_bar_dia_mm)
    return least, most


def legs_needed(width_mm, cover_mm, link_dia_mm, d_mm):
    """Vertical legs across a beam: lateral spacing <= min(600, 0.75 d) and every bar within 150 mm."""
    inside = width_mm - 2.0 * cover_mm - link_dia_mm
    step = min(MAX_LATERAL_LEG_MM, 0.75 * d_mm, 2.0 * MAX_BAR_TO_LEG_MM)
    return max(2, int(math.ceil(inside / step - 1e-9)) + 1)


def beam_review(width_mm, height_mm, cover_mm, link_dia_mm, bar_dia_mm, spacing_mm, legs, fck_mpa,
                label=u'Beam'):
    """
    SMDSC 6.3 review of a beam's links. Returns (pitch to use, notes): a pitch over the maximum is
    brought down to it (and said so); the rest is reported for the designer.
    """
    width_mm, height_mm, cover_mm = float(width_mm), float(height_mm), float(cover_mm)
    link_dia_mm, bar_dia_mm, spacing_mm = float(link_dia_mm), float(bar_dia_mm), float(spacing_mm)
    notes = []
    d = effective_depth_mm(height_mm, cover_mm, link_dia_mm, bar_dia_mm)
    least, most = pitch_limits_mm(d, legs)
    pitch = spacing_mm
    if pitch > most + 1e-6:
        pitch = 25.0 * math.floor(most / 25.0)
        notes.append(u'{}: link pitch {:.0f} mm over the SMDSC 6.3 maximum min(300, 0.75d = {:.0f}): '
                     u'{:.0f} mm used.'.format(label, spacing_mm, 0.75 * d, pitch))
    elif pitch < least - 1e-6:
        notes.append(u'{}: link pitch {:.0f} mm under the SMDSC 6.3 minimum {:.0f} mm (room for the '
                     u'links along the beam).'.format(label, pitch, least))
    if link_dia_mm < MIN_LINK_DIA_MM:
        notes.append(u'{}: H{:.0f} links are under the preferred minimum H8 (SMDSC 6.3).'.format(
            label, link_dia_mm))
    ratio, need = link_ratio(legs, link_dia_mm, pitch, width_mm), rho_w_min(fck_mpa)
    if ratio < need - 1e-9:
        notes.append(u'{}: links H{:.0f} at {:.0f} give Asw/(s bw) = {:.3f} %, under the minimum '
                     u'{:.3f} % (EC2 9.2.2(5), SMDSC 6.3).'.format(label, link_dia_mm, pitch, 100 * ratio,
                                                                      100 * need))
    n_legs = legs_needed(width_mm, cover_mm, link_dia_mm, d)
    if n_legs > legs:
        notes.append(u'{}: {} vertical legs needed across {:.0f} mm (legs at <= min(600, 0.75d), every '
                     u'bar within 150 mm of a leg, SMDSC 6.3): add interior links.'.format(
                         label, n_legs, width_mm))
    if width_mm >= OPEN_LINK_WIDTH_MM:
        notes.append(u'{}: {:.0f} mm wide: open links with a top locking link may be used '
                     u'(SMDSC 6.3, Fig. 6.21).'.format(label, width_mm))
    if height_mm >= SIDE_BARS_DEPTH_MM:
        notes.append(u'{}: {:.0f} mm deep: side bars H16 at <= 250 mm inside the links are needed '
                     u'(SMDSC 6.3, EC2 7.3.3).'.format(label, height_mm))
    return pitch, notes
