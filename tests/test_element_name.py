# -*- coding: utf-8 -*-
"""Revit-free tests for nosa_utils.revit_helpers.element_name fallbacks."""
import os
import sys
import types
import unittest

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from nosa_utils.revit_helpers import element_name  # noqa: E402


class _NoName(object):
    """Mimics a Revit type whose .Name property raises AttributeError."""

    def __init__(self, params=None):
        self._params = params or {}

    @property
    def Name(self):
        raise AttributeError('Name')

    def get_Parameter(self, bip):
        value = self._params.get(bip)
        if value is None:
            return None
        return types.SimpleNamespace(AsString=lambda: value)


class _Named(object):
    Name = u'Type A'


def _stub_revit(getvalue):
    db = types.ModuleType('Autodesk.Revit.DB')
    db.Element = types.SimpleNamespace(Name=types.SimpleNamespace(GetValue=getvalue))
    db.BuiltInParameter = types.SimpleNamespace(ALL_MODEL_TYPE_NAME='ALL_MODEL_TYPE_NAME',
                                                SYMBOL_NAME_PARAM='SYMBOL_NAME_PARAM')
    revit = types.ModuleType('Autodesk.Revit')
    revit.DB = db
    root = types.ModuleType('Autodesk')
    root.Revit = revit
    return {'Autodesk': root, 'Autodesk.Revit': revit, 'Autodesk.Revit.DB': db}


class ElementNameTests(unittest.TestCase):

    def setUp(self):
        self._saved = dict((k, sys.modules.get(k))
                           for k in ('Autodesk', 'Autodesk.Revit', 'Autodesk.Revit.DB'))

    def tearDown(self):
        for key, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = mod

    def _install(self, getvalue):
        sys.modules.update(_stub_revit(getvalue))

    def test_none_returns_empty(self):
        self.assertEqual(element_name(None), u'')

    def test_plain_name_property(self):
        self.assertEqual(element_name(_Named()), u'Type A')

    def test_falls_back_to_element_name_getvalue(self):
        self._install(lambda el: u'Shape 75')
        self.assertEqual(element_name(_NoName()), u'Shape 75')

    def test_falls_back_to_type_name_parameter(self):
        def boom(el):
            raise AttributeError('Name')
        self._install(boom)
        el = _NoName({'SYMBOL_NAME_PARAM': u'H16'})
        self.assertEqual(element_name(el), u'H16')

    def test_all_model_type_name_preferred(self):
        def boom(el):
            raise AttributeError('Name')
        self._install(boom)
        el = _NoName({'ALL_MODEL_TYPE_NAME': u'600x600', 'SYMBOL_NAME_PARAM': u'other'})
        self.assertEqual(element_name(el), u'600x600')

    def test_nothing_readable_returns_empty(self):
        def boom(el):
            raise AttributeError('Name')
        self._install(boom)
        self.assertEqual(element_name(_NoName()), u'')

    def test_no_revit_available_returns_empty(self):
        for key in ('Autodesk', 'Autodesk.Revit', 'Autodesk.Revit.DB'):
            sys.modules.pop(key, None)
        self.assertEqual(element_name(_NoName()), u'')


if __name__ == '__main__':
    unittest.main()
