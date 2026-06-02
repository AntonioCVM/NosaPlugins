# -*- coding: utf-8 -*-
__title__   = "Drawing\nIndex"
__version__ = "1.0"
__doc__     = """Drawing Index Generator v1.0

Generates a complete drawing index from all project sheets.

Shows: Sheet Number, Name, Scale, Revision, Rev Date, Rev Description,
       Drawn By, number of viewports.

Filter by sheet number/name prefix.
Export to CSV (Excel-ready) or HTML (formatted report).
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

ui_module = _lm('drawingidx_ui_local', os.path.join(lib_path, 'ui.py'))
DrawingIndexWindow = ui_module.DrawingIndexWindow

if __name__ == '__main__':
    win = DrawingIndexWindow(revit.doc)
    win.ShowDialog()
