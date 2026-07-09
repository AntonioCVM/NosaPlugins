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
__author__  = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
except (ImportError, AttributeError):
    import imp
    def _lm(n, p):
        m = imp.load_source(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('drawingidx_ui', os.path.join(lib_path, 'ui.py'))

if __name__ == '__main__':
    win = ui_module.DrawingIndexWindow(revit.doc)
    win.ShowDialog()
