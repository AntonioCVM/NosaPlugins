# -*- coding: utf-8 -*-
"""
nosa_utils.water_retaining — water-retaining structures (T8.53, IStructE SMDSC chapter 9, EC2 Part 3), no Revit:
the tightness classes and their minimum wall thickness, the class 1 crack width, cover >= 40 mm, tension bars at
<= 250 mm and distribution bars at <= 150 mm, and the joints that must be drawn.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

MIN_COVER_MM = 40.0
MAX_MAIN_PITCH_MM = 250.0        # tension bars, steel stress <= 150 MPa (SMDSC 9.2.3)
MAX_DISTRIBUTION_PITCH_MM = 150.0
MIN_THICKNESS_MM = {0: 120.0, 1: 150.0, 2: 150.0, 3: 150.0}
CLASSES = (0, 1, 2, 3)


def crack_width_mm(tightness, hydrostatic_head_m=None, wall_mm=None):
    """
    Limiting crack width through the section (SMDSC 9.2.1, Table 9.1): class 1 wk1 = 0.2 mm for hD / hw <= 5
    down to 0.05 mm for >= 25 (linear between); class 2 and 3: through cracks avoided (0.0); class 0: None.
    """
    if tightness == 0:
        return None
    if tightness >= 2:
        return 0.0
    if not hydrostatic_head_m or not wall_mm:
        return 0.2
    ratio = hydrostatic_head_m * 1000.0 / wall_mm
    if ratio <= 5.0:
        return 0.2
    if ratio >= 25.0:
        return 0.05
    return 0.2 - (ratio - 5.0) / 20.0 * 0.15


def review(thickness_mm, cover_mm, main_pitch_mm, distribution_pitch_mm, tightness=1, label=u'Member'):
    """
    SMDSC chapter 9 on a wall or slab of a water-retaining structure. Returns (main pitch, distribution pitch,
    notes): pitches over 250 / 150 come down to them in 25 mm steps; thickness, cover and class are reported.
    """
    notes = []
    least = MIN_THICKNESS_MM.get(tightness, 150.0)
    if thickness_mm < least - 1e-6:
        notes.append(u'{}: {:.0f} mm thick, under the {:.0f} mm of tightness class {} (SMDSC Table 9.1).'.format(
            label, thickness_mm, least, tightness))
    if cover_mm < MIN_COVER_MM - 1e-6:
        notes.append(u'{}: cover {:.0f} mm, under the 40 mm of SMDSC 9.2.2 for water-retaining structures: set the '
                     u'host cover.'.format(label, cover_mm))
    out = []
    for name, pitch, most in ((u'tension', main_pitch_mm, MAX_MAIN_PITCH_MM),
                              (u'distribution', distribution_pitch_mm, MAX_DISTRIBUTION_PITCH_MM)):
        used = pitch
        if pitch > most + 1e-6:
            used = 25.0 * math.floor(most / 25.0)
            notes.append(u'{}: {} bars at {:.0f} over {:.0f} for water-retaining structures: {:.0f} mm used '
                         u'(SMDSC 9.2.3).'.format(label, name, pitch, most, used))
        out.append(used)
    if tightness >= 2:
        notes.append(u'{}: tightness class {}: through cracks to be avoided - liners, water bars or prestress '
                     u'(SMDSC 9.2.1).'.format(label, tightness))
    notes.append(u'{}: water-retaining: show every construction and movement joint on the drawings '
                 u'(SMDSC 9.1, 9.4).'.format(label))
    return out[0], out[1], notes
