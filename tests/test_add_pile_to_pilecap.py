# -*- coding: utf-8 -*-
"""Revit-free tests for AddPileToPilecap config handling and point_in_face (T3.5)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from tests_support import revit_stubs  # noqa: E402

DB, _ = revit_stubs.install_revit_stubs(
    db_attrs={'ElementId': revit_stubs.element_id_namespace()})


def _any_name(name):
    if name.startswith('__'):
        raise AttributeError(name)
    stub = type(name, (object,), {})
    setattr(DB, name, stub)
    return stub


DB.__getattr__ = _any_name  # other DB names are only touched inside functions
revit_stubs.install_system_stubs()
sys.modules['Autodesk.Revit.UI'] = revit_stubs.stub_module('Autodesk.Revit.UI')
sys.modules['Autodesk.Revit.UI.Selection'] = revit_stubs.stub_module(
    'Autodesk.Revit.UI.Selection', {'ISelectionFilter': object})
sys.modules['Autodesk.Revit.Exceptions'] = revit_stubs.stub_module(
    'Autodesk.Revit.Exceptions', {'OperationCanceledException': Exception})

_EXT = os.path.dirname(_LIB)
_LOGIC = os.path.join(_EXT, 'NOSA.tab', 'Foundations.panel', 'PileTools.pulldown',
                      'AddPileToPilecap.pushbutton', 'lib', 'logic.py')
logic = revit_stubs.load_module('addpiletopilecap_logic_test', _LOGIC)


class ConfigTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.legacy = os.path.join(self.tmp, 'add_pile_to_pilecap.json')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _write_legacy(self, data):
        with open(self.legacy, 'w') as f:
            json.dump(data, f)

    def test_defaults_when_nothing_saved(self):
        last = logic.load_last_config({}, legacy_path=self.legacy)
        self.assertEqual(last, {'spacing_mm': logic.DEFAULT_SPACING_MM, 'pile_type': None,
                                'embedment_mm': logic.DEFAULT_EMBEDMENT_MM,
                                'clearance_mm': logic.DEFAULT_CLEARANCE_MM})

    def test_legacy_file_is_read_when_window_config_has_no_values(self):
        self._write_legacy({'last_spacing_mm': 350.0, 'last_pile_type': 'P : 200',
                            'last_embedment_mm': 80.0, 'last_clearance_mm': 120.0})
        last = logic.load_last_config({'win_w': 820.0, 'dark_mode': True},
                                      legacy_path=self.legacy)
        self.assertEqual(last['spacing_mm'], 350.0)
        self.assertEqual(last['pile_type'], 'P : 200')
        self.assertEqual(last['embedment_mm'], 80.0)
        self.assertEqual(last['clearance_mm'], 120.0)

    def test_window_config_wins_over_legacy(self):
        self._write_legacy({'last_spacing_mm': 350.0})
        last = logic.load_last_config({'last_spacing_mm': 900.0}, legacy_path=self.legacy)
        self.assertEqual(last['spacing_mm'], 900.0)
        self.assertEqual(last['embedment_mm'], logic.DEFAULT_EMBEDMENT_MM)

    def test_save_keeps_other_keys_and_round_trips(self):
        cfg = {'dark_mode': True, 'win_w': 820.0}
        logic.save_last_config(cfg, 1200.0, 'P : 300', 75.0, 150.0)
        self.assertTrue(cfg['dark_mode'])
        self.assertEqual(cfg['win_w'], 820.0)
        last = logic.load_last_config(cfg, legacy_path=self.legacy)
        self.assertEqual((last['spacing_mm'], last['pile_type'], last['embedment_mm'],
                          last['clearance_mm']), (1200.0, 'P : 300', 75.0, 150.0))

    def test_save_without_clearance_leaves_previous_clearance(self):
        cfg = {'last_clearance_mm': 99.0}
        logic.save_last_config(cfg, 1200.0, 'P', 75.0)
        self.assertEqual(cfg['last_clearance_mm'], 99.0)

    def test_corrupt_legacy_file_falls_back_to_defaults(self):
        with open(self.legacy, 'w') as f:
            f.write('{not json')
        last = logic.load_last_config({}, legacy_path=self.legacy)
        self.assertEqual(last['spacing_mm'], logic.DEFAULT_SPACING_MM)

    def test_no_config_manager_instance_left(self):
        self.assertFalse(hasattr(logic, 'config'))


class _Proj(object):
    UVPoint = (0.5, 0.5)


class _Face(object):
    def __init__(self, inside):
        self.inside = inside

    def Project(self, point):
        return _Proj() if point is not None else None

    def IsInside(self, uv):
        return self.inside


class _BrokenFace(object):
    def Project(self, point):
        raise RuntimeError('no projection')


class PointInFaceTests(unittest.TestCase):

    def test_inside_and_outside(self):
        self.assertTrue(logic.point_in_face(_Face(True), object()))
        self.assertFalse(logic.point_in_face(_Face(False), object()))

    def test_failed_projection_returns_false_without_name_error(self):
        self.assertFalse(logic.point_in_face(_BrokenFace(), object()))
        self.assertFalse(logic.point_in_face(_Face(True), None))


if __name__ == '__main__':
    unittest.main()
