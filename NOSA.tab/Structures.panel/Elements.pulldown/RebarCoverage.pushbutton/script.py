# -*- coding: utf-8 -*-
__title__   = "Rebar\nCoverage"
__version__ = "1.0"
__doc__     = """Rebar Coverage Checker v1.0

Detects structural elements with no rebar assigned.

Shows:
  - Overall coverage percentage (with / without rebar)
  - Summary table by category
  - Full list of elements missing rebar (select in model)

Export results to CSV for reporting.
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

ui_module = _lm('rebarcov_ui_local', os.path.join(lib_path, 'ui.py'))
RebarCoverageWindow = ui_module.RebarCoverageWindow

if __name__ == '__main__':
    win = RebarCoverageWindow(revit.doc)
    win.ShowDialog()
