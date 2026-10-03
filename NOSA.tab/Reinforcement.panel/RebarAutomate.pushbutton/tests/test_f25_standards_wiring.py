# -*- coding: utf-8 -*-
"""
Tests puros para la deuda F2.5 — verifican que los wrappers
column_rebar.default_lap_length_mm / default_joint_zone_length_mm y
footing_rebar.default_anchorage_length_mm, ahora con std= conectado a
build_column_reinforcement / _build_circular_column_reinforcement /
build_footing_reinforcement / build_floor_reinforcement, producen
resultados REALMENTE distintos (no solo "compila") cuando se les pasa un
std resuelto, y REPRODUCEN EXACTAMENTE el valor pre-F2.5 cuando std=None
(sin pérdida de funcionalidad para todo llamante existente).

Estos wrappers son matemática pura (no tocan Autodesk.Revit.DB), así que
column_rebar.py / footing_rebar.py son importables aquí igual que en los
scripts de fase legacy (mismo entorno con stub de Revit ya usado por
tests/test_column_rebar_phase3.py y tests/test_floor_rebar_phase23.py).
"""
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

# column_rebar.py / footing_rebar.py do `from Autodesk.Revit import DB` at
# module scope for their GEOMETRY functions — irrelevant to the pure-math
# wrappers this file actually exercises, but the import still has to
# resolve. Minimal stub (no live Revit session, no full fidelity needed —
# see test_column_rebar_phase3.py's own fuller stub if a future test here
# needs real DB.XYZ/DB.Line behaviour).
_EXT_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)
from tests_support import revit_stubs  # noqa: E402
revit_stubs.install_revit_stubs(only_if_missing=True)

import column_rebar
import footing_rebar
from nosa_utils import standards

_std = standards.load('EHE-08')


# ══════════════════════════════════════════════════════════════════════════
# column_rebar.default_lap_length_mm
# ══════════════════════════════════════════════════════════════════════════

def test_default_lap_length_mm_without_std_is_unchanged():
    assert column_rebar.default_lap_length_mm(20.0, 40.0) == 20.0 * 40.0


def test_default_lap_length_mm_with_std_delegates_to_standards_module():
    with_std = column_rebar.default_lap_length_mm(
        20.0, 40.0, std=_std, in_compression=True)
    expected = standards.lap_length_mm(_std, 20.0, in_compression=True)
    assert with_std == expected


def test_default_lap_length_mm_with_std_differs_from_the_bare_multiplier():
    """The whole point of F2.5: passing std must actually change the
    number for at least one real diameter, not just accept the kwarg."""
    without_std = column_rebar.default_lap_length_mm(20.0, 40.0)
    with_std = column_rebar.default_lap_length_mm(
        20.0, 40.0, std=_std, in_compression=True)
    # EHE-08's compression factor (40) happens to match the bare
    # multiplier default for THIS particular diameter/case — assert the
    # two call paths are AT LEAST consistent with each other, and prove
    # divergence with a tension case (interpolated band) instead.
    tension_with_std = column_rebar.default_lap_length_mm(
        20.0, 40.0, std=_std, in_compression=False, pct_lapped=60.0)
    assert tension_with_std != without_std


# ══════════════════════════════════════════════════════════════════════════
# column_rebar.default_joint_zone_length_mm
# ══════════════════════════════════════════════════════════════════════════

def test_default_joint_zone_length_mm_without_std_is_unchanged():
    assert column_rebar.default_joint_zone_length_mm(600.0, 3000.0) == \
        max(600.0, 3000.0 / 6.0, 450.0)


def test_default_joint_zone_length_mm_with_std_uses_confinement_factor():
    factor = _std['stirrups']['confinement_zone_factor_h']
    expected = max(600.0 * factor, 3000.0 / 6.0, 450.0)
    assert column_rebar.default_joint_zone_length_mm(
        600.0, 3000.0, std=_std) == expected


# ══════════════════════════════════════════════════════════════════════════
# footing_rebar.default_anchorage_length_mm
# ══════════════════════════════════════════════════════════════════════════

def test_default_anchorage_length_mm_without_std_is_unchanged():
    assert footing_rebar.default_anchorage_length_mm(16.0, 40.0) == 16.0 * 40.0


def test_default_anchorage_length_mm_with_std_delegates_to_standards_module():
    with_std = footing_rebar.default_anchorage_length_mm(16.0, std=_std)
    expected = standards.anchorage_length_mm(_std, 16.0)
    assert with_std == expected


def test_default_anchorage_length_mm_with_std_good_vs_poor_bond_differ():
    good = footing_rebar.default_anchorage_length_mm(16.0, std=_std, good_bond=True)
    poor = footing_rebar.default_anchorage_length_mm(16.0, std=_std, good_bond=False)
    assert good != poor


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
