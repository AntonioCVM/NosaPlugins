# -*- coding: utf-8 -*-
"""nosa_utils.laps — EC2 / BS 8110 anchorage and lap lengths, absolute minimum max(15 phi, 300)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import laps  # noqa: E402


def _close(a, b, tol=0.5):
    return abs(a - b) <= tol


def test_ec2_bond_strength_c32_40():
    # fctm = 0.3 * 32^(2/3) = 3.024; fctd = 0.7 * 3.024 / 1.5 = 1.411; fbd = 2.25 * 1.411 = 3.175
    assert _close(laps.fctm_mpa(32), 3.024, 0.001)
    assert _close(laps.fbd_mpa(32, 16), 3.175, 0.001)
    assert _close(laps.fbd_mpa(32, 16, good_bond=False), 0.7 * 3.175, 0.001)
    assert _close(laps.fbd_mpa(32, 40), 0.92 * 3.175, 0.001)   # eta2 for phi > 32


def test_ec2_lb_rqd_is_about_34_phi_for_c32():
    lb = laps.lb_rqd_mm(16, 32)
    assert _close(lb / 16.0, 34.24, 0.05), lb / 16.0


def test_alpha6_table_8_3():
    assert laps.alpha6(0) == 1.0 and laps.alpha6(25) == 1.0
    assert _close(laps.alpha6(33), 1.15, 1e-9) and _close(laps.alpha6(50), 1.4, 1e-9)
    assert laps.alpha6(51) == 1.5 and laps.alpha6(100) == 1.5


def test_ec2_lap_by_percentage_lapped():
    lb = laps.lb_rqd_mm(16, 32)
    assert _close(laps.lap_mm(16, 32, pct_lapped=100), 1.5 * lb)
    assert _close(laps.lap_mm(16, 32, pct_lapped=50), 1.4 * lb)
    assert _close(laps.lap_mm(16, 32, pct_lapped=0), lb)


def test_absolute_minimum_15_phi_or_300():
    # A small bar in strong concrete would lap below 300 mm by EC2 alone.
    assert laps.lb_rqd_mm(8, 50) < 300
    assert laps.lap_mm(8, 50, pct_lapped=0) == 300.0
    assert laps.lap_mm(8, 50, pct_lapped=0, mode=laps.BS8110) == 300.0
    for dia in (8, 10, 12, 16, 20, 25, 32, 40):
        for fck in (20, 25, 30, 32, 35, 40, 50, 90):
            for mode in (laps.EC2, laps.BS8110):
                for pct in (0, 50, 100):
                    for comp in (False, True):
                        l0 = laps.lap_mm(dia, fck, pct_lapped=pct, in_compression=comp, mode=mode)
                        assert l0 >= max(15 * dia, 300) - 1e-9, (dia, fck, mode, pct, comp, l0)


def test_bs8110_table_3_27():
    assert laps.cube_strength(32) == 40 and laps.cube_strength(30) == 37 and laps.cube_strength(25) == 30
    assert laps.lap_mm(20, 20, mode=laps.BS8110) == 40 * 20            # fcu 25: 40 phi tension
    assert laps.lap_mm(20, 32, mode=laps.BS8110) == 32 * 20            # fcu 40: 32 phi
    assert laps.lap_mm(20, 32, in_compression=True, mode=laps.BS8110) == 25 * 20
    assert _close(laps.lap_mm(20, 32, good_bond=False, mode=laps.BS8110), 1.4 * 32 * 20, 1e-6)


def test_ec2_anchorage_minimum():
    lb = laps.lb_rqd_mm(12, 32)
    assert _close(laps.anchorage_mm(12, 32), lb)
    assert laps.anchorage_mm(6, 90) >= 100.0


def test_fck_from_material_name():
    assert laps.fck_from_material_name(u'Concrete - RC32/40') == 32.0
    assert laps.fck_from_material_name(u'Concrete - Cast-in-Place Concrete RC35/45') == 35.0
    assert laps.fck_from_material_name(u'C30/37 structural') == 30.0
    assert laps.fck_from_material_name(u'Hormigon HA-25') is None
    assert laps.fck_from_material_name(u'Concrete - Generic') is None
    assert laps.fck_from_material_name(None) is None


if __name__ == '__main__':
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            print(name, 'OK')
    print('\nALL LAP CHECKS PASSED')
