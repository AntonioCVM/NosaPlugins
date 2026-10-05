# -*- coding: utf-8 -*-
"""
nosa_utils.laps — anchorage and lap lengths (BS EN 1992-1-1 with UK NA; BS 8110 legacy).

EC2 (8.4, 8.7): lb,rqd = (phi/4)(sigma_sd/fbd), fbd = 2.25 eta1 eta2 fctd,
fctd = alpha_ct 0.7 fctm / gamma_c (UK NA alpha_ct = 1.0), l0 = alpha6 lb,rqd with
alpha1..alpha5 = 1.0 (conservative) and sigma_sd = fyd. BS 8110 (Table 3.27, type 2
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


def anchorage_mm(bar_dia_mm, fck=DEFAULT_FCK_MPA, good_bond=True, in_compression=False, mode=EC2):
    """Design anchorage length of a straight bar (alpha1..alpha5 = 1.0 in EC2)."""
    if mode == BS8110:
        factor = _bs8110_factor(fck, in_compression)
        if not good_bond and not in_compression:
            factor *= _BS8110_POOR_BOND
        return bar_dia_mm * factor
    lb = lb_rqd_mm(bar_dia_mm, fck, good_bond)
    lb_min = max((0.6 if in_compression else 0.3) * lb, 10.0 * bar_dia_mm, 100.0)
    return max(lb, lb_min)


def lap_mm(bar_dia_mm, fck=DEFAULT_FCK_MPA, good_bond=True, pct_lapped=100.0,
           in_compression=False, mode=EC2):
    """Lap length l0, never below max(15 phi, 300 mm)."""
    if mode == BS8110:
        length = anchorage_mm(bar_dia_mm, fck, good_bond, in_compression, BS8110)
    else:
        a6 = alpha6(pct_lapped)
        lb = lb_rqd_mm(bar_dia_mm, fck, good_bond)
        length = max(a6 * lb, 0.3 * a6 * lb, 15.0 * bar_dia_mm, 200.0)
    return max(length, ABS_MIN_LAP_FACTOR * bar_dia_mm, ABS_MIN_LAP_MM)


_CLASS_RE = re.compile(r'(?<![0-9])R?C\s?(\d{2,3})\s?/\s?(\d{2,3})(?![0-9])', re.IGNORECASE)


def fck_from_material_name(name):
    """fck from a strength class in a material name ('Concrete - C32/40' or 'RC32/40' -> 32), else None."""
    match = _CLASS_RE.search(name or u'')
    if not match:
        return None
    fck, fcu = int(match.group(1)), int(match.group(2))
    return float(fck) if 8 <= fck <= 100 and fcu > fck else None
