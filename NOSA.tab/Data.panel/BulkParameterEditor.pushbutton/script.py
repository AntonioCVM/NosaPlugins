# -*- coding: utf-8 -*-
__title__   = "Bulk\nParameter"
__version__ = "2.0"
__doc__     = """Bulk Parameter Editor v2.0

Instances: category ∩ filters ∪ optional Revit selection, parameter scope/filter,
preset JSON, auxiliary read-only column, dry-run preview & logging.
"""
__author__ = "NOSA Engineering"

import sys
import os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)


def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
    except (ImportError, AttributeError):
        import imp
        m = imp.load_source(n, p)
        sys.modules[n] = m
        return m


ui_module = _lm(
    'bulkparam_ui_local',
    os.path.join(lib_path, 'ui.py'))
BulkParameterEditorWindow = ui_module.BulkParameterEditorWindow


if __name__ == '__main__':
    win = BulkParameterEditorWindow(revit.doc, getattr(revit, 'uidoc', None))
    win.ShowDialog()
