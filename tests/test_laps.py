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


# IStructE SMDSC typical tables, lengths in bar diameters for fck 25 / 28 / 30 / 32 (good bond)
_FCK = (25, 28, 30, 32)


def _phi(length_mm, dia=20.0):
    return length_mm / dia


def test_smdsc_table_6_7_walls_alpha3_1():
    """lbd 40/37/36/34 and l0 (alpha6 1.5) 61/56/54/51."""
    for fck, lbd, l0 in zip(_FCK, (40, 37, 36, 34), (61, 56, 54, 51)):
        assert abs(_phi(laps.anchorage_mm(20, fck)) - lbd) <= 0.6, (fck, _phi(laps.anchorage_mm(20, fck)))
        assert abs(_phi(laps.lap_mm(20, fck, pct_lapped=100.0)) - l0) <= 0.6


def test_smdsc_tables_6_4_and_6_5_beams_columns_alpha3_0_9():
    """Beams 36/34/32/31 and l0 (alpha6 1.15) 42/39/37/35; columns l0 (alpha6 1.5) 54/51/48/46."""
    for fck, lb, beam, column in zip(_FCK, (36, 34, 32, 31), (42, 39, 37, 35), (54, 51, 48, 46)):
        assert abs(_phi(laps.anchorage_mm(20, fck, alpha3=0.9)) - lb) <= 0.6
        assert abs(_phi(laps.lap_mm(20, fck, pct_lapped=33.0, alpha3=0.9)) - beam) <= 0.6
        assert abs(_phi(laps.lap_mm(20, fck, pct_lapped=100.0, alpha3=0.9)) - column) <= 0.6


def test_alpha3_is_kept_within_0_7_and_1():
    assert laps.anchorage_mm(20, 30, alpha3=0.5) == laps.anchorage_mm(20, 30, alpha3=0.7)
    assert laps.anchorage_mm(20, 30, alpha3=1.4) == laps.anchorage_mm(20, 30)


def test_smdsc_5_4_3_lap_arrangement():
    assert laps.lap_gap_extension_mm(40.0, 16.0) == 0.0          # within max(4 phi, 50)
    assert laps.lap_gap_extension_mm(80.0, 16.0) == 80.0
    assert laps.adjacent_laps_ok(300.0, 40.0, 1000.0, 16.0)
    assert not laps.adjacent_laps_ok(250.0, 40.0, 1000.0, 16.0)  # < 0.3 l0
    assert not laps.adjacent_laps_ok(300.0, 25.0, 1000.0, 16.0)  # < 2 phi
    assert laps.max_pct_lapped(1) == 100.0 and laps.max_pct_lapped(2) == 50.0


def test_transverse_bars_at_laps_of_20_and_over():
    assert laps.lap_transverse_bars(16.0, 100.0) is None
    assert laps.lap_transverse_bars(20.0, 20.0) is None
    need = laps.lap_transverse_bars(25.0, 100.0, adjacent_clear_mm=200.0)
    assert abs(need['area_mm2'] - 490.9) < 0.1 and need['links']
    # H25 lap 1200, H10 links of 2 legs: a third (400) at 200 holds 3 links = 471 >= 245
    assert laps.lap_transverse_ok(25.0, 100.0, 1200.0, 10.0, 2, 200.0)
    assert not laps.lap_transverse_ok(25.0, 100.0, 1200.0, 6.0, 2, 300.0)


def test_large_bars_and_bundles():
    assert laps.large_bar_notes(32.0, 300.0) == []
    assert len(laps.large_bar_notes(50.0, 600.0)) == 2 and len(laps.large_bar_notes(50.0, 1200.0)) == 1
    phi_n, problems = laps.bundle_equivalent_dia_mm([32.0, 32.0])
    assert abs(phi_n - 45.25) < 0.01 and not problems
    _phi_n, problems = laps.bundle_equivalent_dia_mm([40.0, 40.0, 40.0])
    assert problems                                              # 69 mm > 55
    _phi_n, problems = laps.bundle_equivalent_dia_mm([12.0, 25.0])
    assert problems                                              # ratio > 1.7
