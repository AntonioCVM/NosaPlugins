# -*- coding: utf-8 -*-
"""
nosa_utils.laps — anchorage and lap lengths (BS EN 1992-1-1 with UK NA; BS 8110 legacy).

EC2 (8.4, 8.7): lb,rqd = (phi/4)(sigma_sd/fbd), fbd = 2.25 eta1 eta2 fctd,
fctd = alpha_ct 0.7 fctm / gamma_c (UK NA alpha_ct = 1.0), l0 = alpha6 lb,rqd with
alpha1..alpha5 = 1.0 (conservative; alpha3 may be given, IStructE SMDSC Tables 6.4/6.5 take 0.9 for
beams and columns) and sigma_sd = fyd. SMDSC 5.4.3-5.4.5 arrangement rules (lap gaps, adjacent laps,
lapped percentage, transverse bars at laps, large bars, bundles) are the pure checks at the end. BS 8110 (Table 3.27, type 2
deformed bars): tension / compression multiples by cube strength, x1.4 for poor bond.
Every lap, in either mode, is at least max(15 phi, 300 mm) (user rule 2026-09-30).
Pure Python: no Revit API.
"""
from __future__ import absolute_import, division, print_function, unicode_literals

import math
import re

EC2 = u'ec2'
BS8110 = u'bs8110'

ABS_MIN_LAP_FACTOR = 15.0
ABS_MIN_LAP_MM = 300.0
DEFAULT_FCK_MPA = 32.0
FYK_MPA = 500.0
GAMMA_S = 1.15
GAMMA_C = 1.5
ALPHA_CT = 1.0

# EN 206 strength classes: cylinder fck -> cube fcu.
_CUBE_OF = {12: 15, 16: 20, 20: 25, 25: 30, 28: 35, 30: 37, 32: 40, 35: 45, 40: 50,
            45: 55, 50: 60, 55: 67, 60: 75, 70: 85, 80: 95, 90: 105}

# BS 8110-1 Table 3.27, deformed type 2 bars: fcu -> (tension, compression) multiples of phi.
_BS8110_TABLE = ((25, 40, 32), (30, 37, 29), (35, 34, 27), (40, 32, 25))
_BS8110_POOR_BOND = 1.4


def fctm_mpa(fck):
    if fck <= 50:
        return 0.30 * fck ** (2.0 / 3.0)
    return 2.12 * math.log(1.0 + (fck + 8.0) / 10.0)


def fctd_mpa(fck):
    # EC2 3.1.6(2): fctk,0.05 = 0.7 fctm; strength limited to C60/75 for bond (8.4.2(2)).
    return ALPHA_CT * 0.7 * fctm_mpa(min(fck, 60.0)) / GAMMA_C


def fbd_mpa(fck, bar_dia_mm, good_bond=True):
    eta1 = 1.0 if good_bond else 0.7
    eta2 = 1.0 if bar_dia_mm <= 32 else (132.0 - bar_dia_mm) / 100.0
    return 2.25 * eta1 * eta2 * fctd_mpa(fck)


def lb_rqd_mm(bar_dia_mm, fck, good_bond=True, sigma_sd_mpa=None):
    sigma = FYK_MPA / GAMMA_S if sigma_sd_mpa is None else sigma_sd_mpa
    return bar_dia_mm / 4.0 * sigma / fbd_mpa(fck, bar_dia_mm, good_bond)


def alpha6(pct_lapped):
    """EC2 Table 8.3, interpolated: <25 % 1.0, 33 % 1.15, 50 % 1.4, >50 % 1.5."""
    points = ((25.0, 1.0), (33.0, 1.15), (50.0, 1.4), (100.0, 1.5))
    if pct_lapped <= points[0][0]:
        return 1.0
    for (p0, a0), (p1, a1) in zip(points, points[1:]):
        if pct_lapped <= p1:
            if p1 == 100.0:
                return 1.5 if pct_lapped > 50.0 else a0
            return a0 + (a1 - a0) * (pct_lapped - p0) / (p1 - p0)
    return 1.5


def cube_strength(fck):
    """fcu of the EN 206 class with this fck (nearest lower class)."""
    keys = sorted(_CUBE_OF)
    best = keys[0]
    for k in keys:
        if k <= fck + 1e-6:
            best = k
    return _CUBE_OF[best]


def _bs8110_factor(fck, in_compression):
    fcu = cube_strength(fck)
    row = _BS8110_TABLE[0]
    for entry in _BS8110_TABLE:
        if fcu >= entry[0]:
            row = entry
    return row[2] if in_compression else row[1]


def _confinement(alpha3):
    """alpha3 within EC2 Table 8.2 (0.7..1.0); alpha2 = alpha5 = 1 so alpha2.alpha3.alpha5 >= 0.7 holds."""
    return min(1.0, max(0.7, alpha3))


def anchorage_mm(bar_dia_mm, fck=DEFAULT_FCK_MPA, good_bond=True, in_compression=False, mode=EC2,
                 alpha3=1.0):
    """Design anchorage length of a straight bar (alpha1, alpha2, alpha4, alpha5 = 1.0 in EC2)."""
    if mode == BS8110:
        factor = _bs8110_factor(fck, in_compression)
        if not good_bond and not in_compression:
            factor *= _BS8110_POOR_BOND
        return bar_dia_mm * factor
    lb = lb_rqd_mm(bar_dia_mm, fck, good_bond)
    lb_min = max((0.6 if in_compression else 0.3) * lb, 10.0 * bar_dia_mm, 100.0)
    return max(_confinement(alpha3) * lb, lb_min)


def lap_mm(bar_dia_mm, fck=DEFAULT_FCK_MPA, good_bond=True, pct_lapped=100.0,
           in_compression=False, mode=EC2, alpha3=1.0):
    """Lap length l0, never below max(15 phi, 300 mm)."""
    if mode == BS8110:
        length = anchorage_mm(bar_dia_mm, fck, good_bond, in_compression, BS8110)
    else:
        a6 = alpha6(pct_lapped)
        lb = lb_rqd_mm(bar_dia_mm, fck, good_bond)
        length = max(_confinement(alpha3) * a6 * lb, 0.3 * a6 * lb, 15.0 * bar_dia_mm, 200.0)
    return max(length, ABS_MIN_LAP_FACTOR * bar_dia_mm, ABS_MIN_LAP_MM)


_CLASS_RE = re.compile(r'(?<![0-9])R?C\s?(\d{2,3})\s?/\s?(\d{2,3})(?![0-9])', re.IGNORECASE)


def fck_from_material_name(name):
    """fck from a strength class in a material name ('Concrete - C32/40' or 'RC32/40' -> 32), else None."""
    match = _CLASS_RE.search(name or u'')
    if not match:
        return None
    fck, fcu = int(match.group(1)), int(match.group(2))
    return float(fck) if 8 <= fck <= 100 and fcu > fck else None


# ── IStructE SMDSC 5.4.3-5.4.5 (EC2 8.7, 8.8, 8.9): arrangement of laps ──────────────────────────

def lap_gap_extension_mm(clear_gap_mm, bar_dia_mm):
    """Extra lap length when the lapped bars are more than max(4 phi, 50) apart: the clear gap itself."""
    return clear_gap_mm if clear_gap_mm > max(4.0 * bar_dia_mm, 50.0) else 0.0


def adjacent_laps_ok(longitudinal_gap_mm, clear_between_mm, lap_length_mm, bar_dia_mm):
    """Adjacent laps: ends at least 0.3 l0 apart and bars at least max(2 phi, 20) clear."""
    return (longitudinal_gap_mm >= 0.3 * lap_length_mm - 1e-6
            and clear_between_mm >= max(2.0 * bar_dia_mm, 20.0) - 1e-6)


def max_pct_lapped(layers):
    """Bars in tension lapped in one section: 100 % in a single layer, 50 % when in several."""
    return 100.0 if layers <= 1 else 50.0


def lap_transverse_bars(bar_dia_mm, pct_lapped, adjacent_clear_mm=None):
    """
    Transverse reinforcement a tension lap needs (SMDSC 5.4.3): None when the links there for other
    reasons do (phi < 20 or < 25 % lapped); else {'area_mm2': sum Ast >= As of one bar, half within
    each outer third of the lap, 'links': True when > 50 % lapped with laps <= 10 phi apart (links or
    U-bars anchored into the section)}.
    """
    if bar_dia_mm < 20.0 or pct_lapped < 25.0:
        return None
    links = pct_lapped > 50.0 and adjacent_clear_mm is not None and adjacent_clear_mm <= 10.0 * bar_dia_mm
    return {'area_mm2': math.pi * bar_dia_mm ** 2 / 4.0, 'links': links}


def lap_transverse_ok(bar_dia_mm, pct_lapped, lap_length_mm, link_dia_mm, link_legs, link_spacing_mm):
    """True when the links crossing a lap give sum Ast >= As of one lapped bar in its outer thirds."""
    need = lap_transverse_bars(bar_dia_mm, pct_lapped)
    if need is None:
        return True
    per_third = int(math.floor((lap_length_mm / 3.0) / link_spacing_mm + 1e-9)) + 1 if link_spacing_mm > 0 else 0
    area = per_third * link_legs * math.pi * link_dia_mm ** 2 / 4.0
    return area >= need['area_mm2'] / 2.0 - 1e-6


def large_bar_notes(bar_dia_mm, min_section_mm):
    """SMDSC 5.4.4 / EC2 8.8: bars over 40 mm are not lapped unless the section is at least 1 m."""
    notes = []
    if bar_dia_mm > 40.0:
        notes.append(u'H{:.0f} is a large bar: prefer mechanical anchorages, add confining links '
                     u'(EC2 8.8).'.format(bar_dia_mm))
        if min_section_mm < 1000.0:
            notes.append(u'H{:.0f} must not be lapped in a section under 1 m (EC2 8.8(4)): use '
                         u'couplers.'.format(bar_dia_mm))
    return notes


def bundle_equivalent_dia_mm(bar_dias_mm, lapped=False, vertical_compression=False):
    """
    EC2 8.9.1: phi_n = phi sqrt(n_b) <= 55 mm (from the bundle's area); n_b <= 4 for vertical bars in
    compression and bars in a lapped joint, else <= 3; diameters in a bundle within a ratio of 1.7.
    Returns (phi_n, [problems]).
    """
    n = len(bar_dias_mm)
    area = sum(math.pi * d ** 2 / 4.0 for d in bar_dias_mm)
    phi_n = math.sqrt(4.0 * area / math.pi)
    problems = []
    if phi_n > 55.0 + 1e-6:
        problems.append(u'equivalent diameter {:.0f} mm over 55 mm'.format(phi_n))
    if n > (4 if (lapped or vertical_compression) else 3):
        problems.append(u'{} bars in a bundle (max {})'.format(n, 4 if (lapped or vertical_compression) else 3))
    if n and max(bar_dias_mm) > 1.7 * min(bar_dias_mm) + 1e-6:
        problems.append(u'bar sizes in a bundle more than 1.7 apart')
    return phi_n, problems
