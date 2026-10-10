# -*- coding: utf-8 -*-
"""
nosa_utils.fabric — welded fabric to BS 4483 (T8.51, IStructE SMDSC 4.2.5, 5.1.10, 5.4.6), no Revit: the
designated fabrics and their wires, laps of main wires (a tension lap, alpha3 = 1.0) and of secondary wires
(SMDSC Table 5.8), the sheets an area needs, the lightest fabric for a steel area and the rows of a fabric
schedule (SMDSC Table 4.3).
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math

SHEET_LENGTH_MM, SHEET_WIDTH_MM = 4800.0, 2400.0
GROUND_SLAB_FABRIC = u'A193'

# reference: (main wire mm, main pitch mm, cross wire mm, cross pitch mm)
FABRICS = {
    u'A393': (10.0, 200.0, 10.0, 200.0), u'A252': (8.0, 200.0, 8.0, 200.0), u'A193': (7.0, 200.0, 7.0, 200.0),
    u'A142': (6.0, 200.0, 6.0, 200.0), u'A98': (5.0, 200.0, 5.0, 200.0),
    u'B1131': (12.0, 100.0, 8.0, 200.0), u'B785': (10.0, 100.0, 8.0, 200.0), u'B503': (8.0, 100.0, 8.0, 200.0),
    u'B385': (7.0, 100.0, 7.0, 200.0), u'B283': (6.0, 100.0, 7.0, 200.0), u'B196': (5.0, 100.0, 7.0, 200.0),
    u'C785': (10.0, 100.0, 6.0, 400.0), u'C636': (9.0, 100.0, 6.0, 400.0), u'C503': (8.0, 100.0, 5.0, 400.0),
    u'C385': (7.0, 100.0, 5.0, 400.0), u'C283': (6.0, 100.0, 5.0, 400.0),
    u'D98': (5.0, 200.0, 5.0, 200.0), u'D49': (2.5, 100.0, 2.5, 100.0),
}


def references(kind=None):
    """Designations, heaviest first within each type (A, B, C, D), or of one type."""
    refs = [r for r in FABRICS if kind is None or r.startswith(kind)]
    return sorted(refs, key=lambda r: (r[0], -area_per_m(r)[0]))


def area_per_m(ref):
    """(main, cross) mm2/m of a fabric."""
    main, mp, cross, cp = FABRICS[ref]
    return (math.pi * main ** 2 / 4.0 * 1000.0 / mp, math.pi * cross ** 2 / 4.0 * 1000.0 / cp)


def secondary_lap_mm(cross_dia_mm, cross_pitch_mm):
    """SMDSC Table 5.8: >= 150 (1 pitch) up to 6 mm, >= 250 (2 pitches) to 8.5, >= 350 (2 pitches) to 12."""
    if cross_dia_mm <= 6.0:
        return max(150.0, cross_pitch_mm)
    if cross_dia_mm <= 8.5:
        return max(250.0, 2.0 * cross_pitch_mm)
    return max(350.0, 2.0 * cross_pitch_mm)


def main_lap_mm(ref, fck_mpa=30.0, good_bond=True):
    """Lap of the main wires, intermeshed: a full tension lap with alpha3 = 1.0 (SMDSC 5.4.6), up to 5 mm."""
    from nosa_utils import laps
    lap = laps.lap_mm(FABRICS[ref][0], fck_mpa, good_bond, 100.0, alpha3=1.0)
    return 5.0 * math.ceil(lap / 5.0 - 1e-9)


def laps_mm(ref, fck_mpa=30.0, good_bond=True):
    """(main, secondary) laps of a fabric; a square A or D fabric laps both ways like its main wires."""
    main = main_lap_mm(ref, fck_mpa, good_bond)
    if ref[0] in u'AD':
        return main, main
    return main, secondary_lap_mm(FABRICS[ref][2], FABRICS[ref][3])


def sheets(length_mm, width_mm, main_lap_mm_, cross_lap_mm):
    """Sheets of 4.8 x 2.4 m covering length (along the main wires) x width with the laps between them."""
    def count(extent, size, lap):
        return 1 if extent <= size else int(math.ceil((extent - lap) / (size - lap) - 1e-9))
    return count(length_mm, SHEET_LENGTH_MM, main_lap_mm_) * count(width_mm, SHEET_WIDTH_MM, cross_lap_mm)


def lightest(main_mm2_per_m, cross_mm2_per_m=0.0, kinds=u'ABC'):
    """The lightest designated fabric giving both areas (ties broken by the type order), or None."""
    fits = [r for r in FABRICS if r[0] in kinds and area_per_m(r)[0] >= main_mm2_per_m - 1e-6
            and area_per_m(r)[1] >= cross_mm2_per_m - 1e-6]
    if not fits:
        return None
    return min(fits, key=lambda r: (sum(area_per_m(r)), r))


def sheet_mass_kg(ref):
    """Mass of one 4.8 x 2.4 m sheet from its wires (steel 7850 kg/m3)."""
    main, mp, cross, cp = FABRICS[ref]
    return (math.pi * main ** 2 / 4.0 * (SHEET_WIDTH_MM / mp) * SHEET_LENGTH_MM +
            math.pi * cross ** 2 / 4.0 * (SHEET_LENGTH_MM / cp) * SHEET_WIDTH_MM) * 1e-9 * 7850.0


def schedule_rows(entries):
    """
    SMDSC Table 4.3 fabric schedule: entries [(member, mark, ref, sheets)] -> rows sorted by member and mark,
    each (member, mark, ref, 'L x W', sheets, mass kg) with the sheet's mass from its wires (7850 kg/m3).
    """
    rows = []
    for member, mark, ref, n in sorted(entries, key=lambda e: (e[0], e[1])):
        steel = sheet_mass_kg(ref)
        rows.append((member, mark, ref, u'{:.0f} x {:.0f}'.format(SHEET_LENGTH_MM, SHEET_WIDTH_MM), n,
                     round(steel * n, 1)))
    return rows
