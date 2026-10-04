# -*- coding: utf-8 -*-
"""
Pure tests for Phase F2: nosa_utils.standards — profile loading,
deep_merge, the 5 calculation helpers against known EHE-08 values, and
schema validation of all 3 shipped profiles.

Runs OUTSIDE Revit — no Autodesk.Revit / pyrevit required.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import standards  # noqa: E402

_USER_OVERRIDE_DIR = os.path.abspath(
    os.path.join(_HERE, '..', '..', '..', '..', 'NOSA_Configs', 'rebar_standards'))


# ══════════════════════════════════════════════════════════════════════════
# list_available / load
# ══════════════════════════════════════════════════════════════════════════

def test_list_available_returns_exactly_the_3_f2_profiles():
    assert standards.list_available() == ['BS-8666-2020', 'EHE-08', 'EN-ISO-3766']


def test_load_ehe08_returns_the_expected_top_level_shape():
    std = standards.load('EHE-08')
    assert std['code'] == u'EHE-08'
    assert std['shape_catalog'] == u'en_iso_3766'
    assert std['units'] == u'mm'


def test_load_unknown_code_raises():
    try:
        standards.load('DOES-NOT-EXIST')
        assert False, 'expected an IOError/OSError for a profile that is not shipped'
    except (IOError, OSError):  # nosa-lint: disable=NOSA006 - test cleanup, failure is irrelevant
        pass


# ══════════════════════════════════════════════════════════════════════════
# deep_merge
# ══════════════════════════════════════════════════════════════════════════

def test_deep_merge_overrides_a_nested_leaf_without_dropping_siblings():
    base = {'a': 1, 'nested': {'x': 1, 'y': 2, 'z': 3}}
    user = {'nested': {'y': 99}}
    merged = standards.deep_merge(base, user)
    assert merged == {'a': 1, 'nested': {'x': 1, 'y': 99, 'z': 3}}


def test_deep_merge_does_not_mutate_its_inputs():
    base = {'nested': {'x': 1}}
    user = {'nested': {'x': 2}}
    standards.deep_merge(base, user)
    assert base == {'nested': {'x': 1}}
    assert user == {'nested': {'x': 2}}


def test_deep_merge_adds_a_brand_new_key_from_user():
    base = {'a': 1}
    user = {'b': 2}
    assert standards.deep_merge(base, user) == {'a': 1, 'b': 2}


def test_load_with_a_real_user_override_file_merges_correctly():
    """End-to-end: writes a real NOSA_Configs/rebar_standards/EHE-08.json
    override, confirms load() picks it up and merges it, then cleans
    up — the override directory does not exist in a fresh checkout."""
    if not os.path.isdir(_USER_OVERRIDE_DIR):
        os.makedirs(_USER_OVERRIDE_DIR)
    override_path = os.path.join(_USER_OVERRIDE_DIR, u'EHE-08.json')
    override_existed_before = os.path.isfile(override_path)
    previous_content = None
    if override_existed_before:
        with open(override_path, 'r', encoding='utf-8') as f:
            previous_content = f.read()
    try:
        with open(override_path, 'w', encoding='utf-8') as f:
            json.dump({'cover_mm': {'by_element': {'column': 999.0}}}, f)
        std = standards.load('EHE-08')
        assert standards.cover_for(std, 'column') == 999.0
        assert standards.cover_for(std, 'foundation') == 70.0  # untouched sibling survives
    finally:
        if override_existed_before:
            with open(override_path, 'w', encoding='utf-8') as f:
                f.write(previous_content)
        else:
            os.remove(override_path)


# ══════════════════════════════════════════════════════════════════════════
# Calculation helpers — known EHE-08 values
# ══════════════════════════════════════════════════════════════════════════

_std = standards.load('EHE-08')


def test_cover_for_by_element():
    assert standards.cover_for(_std, 'foundation') == 70.0
    assert standards.cover_for(_std, 'column') == 35.0
    assert standards.cover_for(_std, 'beam') == 30.0
    assert standards.cover_for(_std, 'slab') == 25.0
    assert standards.cover_for(_std, 'wall') == 30.0
    assert standards.cover_for(_std, 'pile_cap') == 75.0


def test_cover_for_exposure_takes_priority_over_element_kind():
    assert standards.cover_for(_std, 'foundation', exposure='IIIa') == 35.0
    assert standards.cover_for(_std, 'foundation', exposure='IV') == 45.0


def test_cover_for_unknown_kind_returns_none_not_a_guess():
    assert standards.cover_for(_std, 'nonexistent_kind') is None


def test_mandrel_diameter_mm_picks_the_right_bracket():
    assert standards.mandrel_diameter_mm(_std, 12.0, is_stirrup=False) == 12.0 * 4
    assert standards.mandrel_diameter_mm(_std, 16.0, is_stirrup=False) == 16.0 * 4
    assert standards.mandrel_diameter_mm(_std, 20.0, is_stirrup=False) == 20.0 * 7
    assert standards.mandrel_diameter_mm(_std, 25.0, is_stirrup=False) == 25.0 * 7
    assert standards.mandrel_diameter_mm(_std, 32.0, is_stirrup=False) == 32.0 * 10


def test_mandrel_diameter_mm_stirrup_vs_bar_factor_differ_in_top_bracket():
    # bar_max_mm=40 bracket: stirrup_factor=8, bar_factor=10 — must differ.
    assert standards.mandrel_diameter_mm(_std, 32.0, is_stirrup=True) == 32.0 * 8
    assert standards.mandrel_diameter_mm(_std, 32.0, is_stirrup=False) == 32.0 * 10


def test_mandrel_diameter_mm_falls_back_to_largest_bracket_beyond_catalogue():
    assert standards.mandrel_diameter_mm(_std, 100.0, is_stirrup=False) == 100.0 * 10


def test_lap_length_mm_tension_bands():
    assert standards.lap_length_mm(_std, 16.0, pct_lapped=25.0) == standards.round_up_mm(16.0 * 40)
    assert standards.lap_length_mm(_std, 16.0, pct_lapped=10.0) == standards.round_up_mm(16.0 * 40)
    assert standards.lap_length_mm(_std, 16.0, pct_lapped=60.0) == standards.round_up_mm(16.0 * 57)
    # Interpolated band (25% < pct_lapped <= 50%) — 37.5% is the midpoint.
    mid = standards.lap_length_mm(_std, 16.0, pct_lapped=37.5)
    assert mid == standards.round_up_mm(16.0 * ((40 + 57) / 2.0))  # laps detailed in 25 mm steps


def test_lap_length_mm_compression_uses_its_own_factor():
    assert standards.lap_length_mm(_std, 16.0, in_compression=True) == standards.round_up_mm(16.0 * 40)


def test_lap_length_mm_clamps_to_min_mm():
    # Absolute minimum max(15 phi, 300 mm) for every lap (user rule 2026-09-30).
    assert standards.lap_length_mm(_std, 1.0) == 300.0
    assert standards.lap_length_mm(_std, 25.0, pct_lapped=0.0) >= 25.0 * 15


def test_anchorage_length_mm_good_vs_poor_bond():
    assert standards.anchorage_length_mm(_std, 16.0, good_bond=True) == standards.round_up_mm(16.0 * 40)
    assert standards.anchorage_length_mm(_std, 16.0, good_bond=False) == standards.round_up_mm(16.0 * 57)


def test_anchorage_length_mm_compression_applies_the_reduction_factor():
    expected = standards.round_up_mm(16.0 * 40 * 0.7)
    assert abs(standards.anchorage_length_mm(
        _std, 16.0, good_bond=True, in_compression=True) - expected) < 1e-9


def test_anchorage_length_mm_clamps_to_min_mm():
    assert standards.anchorage_length_mm(_std, 1.0, good_bond=True) == 150.0


def test_hook_extension_mm_known_angles():
    assert standards.hook_extension_mm(_std, 16.0, 90) == 16.0 * 12
    assert standards.hook_extension_mm(_std, 16.0, 135) == 16.0 * 10
    # 16mm * factor 4 = 64mm, BELOW min_hook_extension_mm (70) -- the
    # min clamp applies here too, matching the function's own contract.
    assert standards.hook_extension_mm(_std, 16.0, 180) == 70.0


def test_hook_extension_mm_clamps_to_minimum():
    assert standards.hook_extension_mm(_std, 1.0, 90) == 70.0


def test_hook_extension_mm_unknown_angle_raises():
    try:
        standards.hook_extension_mm(_std, 16.0, 47)
        assert False, 'expected KeyError for an undeclared hook angle'
    except KeyError:  # nosa-lint: disable=NOSA006 - test cleanup, failure is irrelevant
        pass


# ══════════════════════════════════════════════════════════════════════════
# Schema validation — the 3 shipped profiles
# ══════════════════════════════════════════════════════════════════════════

def test_all_3_profiles_validate_against_the_schema():
    for code in ('EHE-08', 'EN-ISO-3766', 'BS-8666-2020'):
        std = standards.load(code)
        is_valid, errors = standards.validate_profile(std)
        assert is_valid, u'{} failed schema validation: {}'.format(code, errors)


def test_validate_profile_catches_a_missing_required_key():
    broken = standards.load('EHE-08')
    del broken['cover_mm']
    is_valid, errors = standards.validate_profile(broken)
    assert not is_valid
    assert errors


def test_validate_profile_catches_a_missing_nested_required_key():
    broken = standards.load('EHE-08')
    del broken['anchorage']['basic_length_factor']['good_bond']
    is_valid, errors = standards.validate_profile(broken)
    assert not is_valid
    assert errors


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(u'{}: OK'.format(t.__name__))
        except Exception as e:
            failures += 1
            print(u'{}: FAILED -- {}'.format(t.__name__, e))
    print(u'\n{}/{} tests passed'.format(len(tests) - failures, len(tests)))
    sys.exit(1 if failures else 0)
