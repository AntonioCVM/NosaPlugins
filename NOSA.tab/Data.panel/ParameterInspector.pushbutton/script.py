# -*- coding: utf-8 -*-
__title__   = "Parameter\nInspector"
__version__ = "1.0"
__doc__     = """Parameter Inspector v1.0

Explore, compare and bulk-edit parameters on selected elements.

Features:
  - Shows ALL parameters (Built-in, Shared, Project) for selected elements
  - Real-time search/filter by parameter name
  - Highlights differences between elements (red = inconsistent value)
  - Bulk edit: set same value to all selected elements at once
  - Copy from source: copy all writable params from one element to selection
  - Export parameter table to CSV
"""
__author__ = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path: sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('paraminspector_ui_local', os.path.join(lib_path, 'ui.py'))
ParameterInspectorWindow = ui_module.ParameterInspectorWindow

if __name__ == '__main__':
    win = ParameterInspectorWindow(revit.doc)
    win.ShowDialog()
