# -*- coding: utf-8 -*-
"""Revit-free checks of the model-name and category matching helpers in clash_locator."""
import importlib.util
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load_locator():
    stubs = {}
    for name in ('Autodesk', 'Autodesk.Revit', 'Autodesk.Revit.DB', 'nosa_utils',
                 'nosa_utils.revit_helpers', 'nosa_utils.telemetry'):
        stubs[name] = types.ModuleType(name)
    stubs['Autodesk'].Revit = stubs['Autodesk.Revit']
    stubs['Autodesk.Revit'].DB = stubs['Autodesk.Revit.DB']
    helpers, telemetry = stubs['nosa_utils.revit_helpers'], stubs['nosa_utils.telemetry']
    helpers.get_id_value = helpers.element_id_from_int = helpers.element_name = lambda x: x
    telemetry.log_swallowed = lambda *a, **k: None
    saved = dict((k, sys.modules.get(k)) for k in stubs)
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            'clash_locator_under_test', os.path.join(_HERE, '..', 'lib', 'clash_locator.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


loc = _load_locator()


class ModelNameTests(unittest.TestCase):
    def test_same_code_different_suffix(self):
        self.assertTrue(loc.names_match(u'UWWTP-NE-10-ST-MD-00001.nwc',
                                        u'UWWTP-NE-10-ST-MD-00001_detached_antonio.rvt'))

    def test_link_instance_name(self):
        self.assertTrue(loc.names_match(u'LinkSource.nwc', u'LinkSource.rvt : 1 : location Origin'))

    def test_different_discipline_does_not_match(self):
        self.assertFalse(loc.names_match(u'UWWTP-NE-10-ST-MD-00001.nwc', u'UWWTP-NE-10-AR-MD-00001.rvt'))
        self.assertFalse(loc.names_match(u'UWWTP-NE-10-ST-MD-00001.nwc', u'UWWTP-NE-11-ST-MD-00001.rvt'))

    def test_path_and_case(self):
        self.assertTrue(loc.names_match(u'c:\\models\\uwwtp-ne-10-st-md-00001.RVT', u'UWWTP-NE-10-ST-MD-00001'))

    def test_empty_never_matches(self):
        self.assertFalse(loc.names_match(u'', u'X'))
        self.assertFalse(loc.names_match(u'X', None))

    def test_short_prefix_is_not_enough(self):
        self.assertFalse(loc.names_match(u'Model.nwc', u'Model-structure-big.rvt'))


class CategoryWordTests(unittest.TestCase):
    def test_plural_and_enum_forms_agree(self):
        self.assertEqual(loc._words(u'Slab Edges'), loc._words(u'OST_EdgeSlab'))
        self.assertEqual(loc._words(u'Structural Foundations'), loc._words(u'OST_StructuralFoundation'))
        self.assertEqual(loc._words(u'Generic Models'), loc._words(u'OST_GenericModel'))
        self.assertEqual(loc._words(u'Walls'), loc._words(u'OST_Walls'))

    def test_different_categories_differ(self):
        self.assertNotEqual(loc._words(u'Floors'), loc._words(u'Walls'))
        self.assertNotEqual(loc._words(u'Structural Framing'), loc._words(u'Structural Columns'))


if __name__ == '__main__':
    unittest.main()
