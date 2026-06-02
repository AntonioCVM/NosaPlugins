# -*- coding: utf-8 -*-
__title__   = "Connection\nChecker"
__version__ = "1.0"
__doc__     = """Structural Connection Checker v1.0

Verifies structural element connections and analytical model settings:

  Analytical model disabled  — columns/beams excluded from analysis
  Structural usage empty     — beams with undefined structural role
  Column attachment missing  — columns not attached to base/top level
  Beam end — no adjacent element  — beam endpoint with nothing connected

Row colours: red = High, orange = Medium.
Select in model + CSV export.
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

ui_module = _lm('connchk_ui_local', os.path.join(lib_path, 'ui.py'))
ConnectionCheckerWindow = ui_module.ConnectionCheckerWindow

if __name__ == '__main__':
    win = ConnectionCheckerWindow(revit.doc)
    win.ShowDialog()
