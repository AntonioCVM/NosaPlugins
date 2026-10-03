# -*- coding: utf-8 -*-
"""
Pure tests for nosa_utils.revit_compat — Phase F0.

Runs OUTSIDE Revit (no Autodesk.Revit / pyrevit required). This is the
first "puro (pytest)" test level from the blueprint's Part 15 — the
matrix's own smoke-in-Revit level (2024/2025/2026/2027) is a separate,
manual step that needs a live Revit session and is NOT what this file
verifies.

Run with:
    pytest NOSA.tab/Reinforcement.panel/RebarAutomate.pushbutton/tests/test_revit_compat.py
or directly:
    python NOSA.tab/Reinforcement.panel/RebarAutomate.pushbutton/tests/test_revit_compat.py
"""
import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils import revit_compat  # noqa: E402


def test_module_imports_without_revit():
    """
    F0 rule (c): this module must import cleanly with no live Revit
    session — no Autodesk.Revit / pyrevit installed at all. If this
    test file itself imported successfully (see the module-level
    `import` above), the rule already holds; this test additionally
    checks the module-level globals degraded correctly instead of
    raising during import.
    """
    assert revit_compat.YEAR is None or isinstance(revit_compat.YEAR, int)
    assert isinstance(revit_compat.IS_2025_PLUS, bool)


def test_revit_year_returns_none_outside_revit():
    assert revit_compat.revit_year() is None
    assert revit_compat.revit_year(app=None) is None
    # An app-like object without a usable VersionNumber degrades to
    # None too, rather than raising.
    class _NotRevit(object):
        pass
    assert revit_compat.revit_year(_NotRevit()) is None


def test_revit_year_reads_version_number_directly():
    class _FakeApp(object):
        VersionNumber = '2026'
    assert revit_compat.revit_year(_FakeApp()) == 2026


def test_revit_year_reads_version_number_via_application():
    class _FakeInnerApp(object):
        VersionNumber = '2024'
    class _FakeUIApp(object):
        Application = _FakeInnerApp()
    assert revit_compat.revit_year(_FakeUIApp()) == 2024


def test_api_selects_2024_baseline_for_2024():
    c = revit_compat.api(year=2024)
    assert isinstance(c, revit_compat._ApiBase)
    assert not isinstance(c, revit_compat._Api2025Plus)


def test_api_selects_2025plus_for_2025_2026_2027():
    for year in (2025, 2026, 2027):
        c = revit_compat.api(year=year)
        assert isinstance(c, revit_compat._Api2025Plus), \
            'api(year={}) must return the 2025+ facade'.format(year)


def test_api_falls_back_to_2024_baseline_with_no_year_available():
    # Outside Revit, YEAR is None -- api() with no explicit year must
    # not raise, and must degrade to the safe 2024 baseline (every
    # later-year facade is additive, per the module's own docstring).
    c = revit_compat.api()
    assert isinstance(c, revit_compat._ApiBase)


def test_to_internal_from_internal_roundtrip_uses_304_8():
    c = revit_compat.api(year=2024)
    assert abs(c.to_internal(304.8) - 1.0) < 1e-12
    assert abs(c.from_internal(1.0) - 304.8) < 1e-12
    for mm in (0.0, 1.0, 40.0, 12000.0, -50.0):
        assert abs(c.from_internal(c.to_internal(mm)) - mm) < 1e-9


def test_bar_diameter_tries_names_in_order():
    c = revit_compat.api(year=2024)

    class _Current(object):
        BarModelDiameter = 0.05
    assert c.bar_diameter(_Current()) == 0.05

    class _Legacy(object):
        BarNominalDiameter = 0.06
    assert c.bar_diameter(_Legacy()) == 0.06

    class _Obsolete(object):
        BarDiameter = 0.07
    assert c.bar_diameter(_Obsolete()) == 0.07

    class _Nothing(object):
        pass
    try:
        c.bar_diameter(_Nothing())
        assert False, 'expected AttributeError when no diameter attribute exists at all'
    except AttributeError:
        pass


def test_bip_alias_table_is_empty_by_design():
    # PHASE F0 rule (b) — no alias guessed ahead of evidence.
    assert revit_compat._ApiBase._BIP_ALIASES == {}


def test_get_id_value_standalone_no_revit_helpers_dependency():
    assert revit_compat.get_id_value(None) == 0

    class _Modern(object):
        Value = 123
    assert revit_compat.get_id_value(_Modern()) == 123

    class _Legacy(object):
        IntegerValue = 456
    assert revit_compat.get_id_value(_Legacy()) == 456


if __name__ == '__main__':
    # Allow running this file directly (python test_revit_compat.py)
    # without a pytest install, matching this project's existing
    # scratchpad-test convention.
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
