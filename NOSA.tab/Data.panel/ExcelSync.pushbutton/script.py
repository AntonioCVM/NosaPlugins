# -*- coding: utf-8 -*-
__title__   = "Excel\nSync"
__version__ = "1.0"
__doc__     = """Excel Sync v1.0

Import CSV data and map columns to Revit parameters.

Features:
  - Load any CSV file and preview its contents
  - Choose key column (Mark or UniqueId) to match elements
  - Map CSV columns to Revit parameter names
  - Preview matched elements before applying
  - Apply values to multiple elements in one transaction
"""
__author__ = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('excelsync_ui_local', os.path.join(lib_path, 'ui.py'))
ExcelSyncWindow = ui_module.ExcelSyncWindow

if __name__ == '__main__':
    win = ExcelSyncWindow(revit.doc)
    win.ShowDialog()
