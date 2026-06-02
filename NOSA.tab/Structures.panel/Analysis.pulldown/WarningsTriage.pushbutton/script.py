# -*- coding: utf-8 -*-
__title__   = "Warnings\nTriage"
__version__ = "1.0"
__doc__     = """Structural Warnings Triage v1.0

Classifies all Revit model warnings by structural impact:
  - High: overlaps, analytical issues, duplicates, positioning
  - Medium: joins, rebar, floors, walls, columns
  - Low: rooms, informational

Shows affected elements, suggested action, and lets you:
  - Select elements in model
  - Ignore reviewed warnings
  - Export to CSV
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

ui_module = _lm('wtriage_ui_local', os.path.join(lib_path, 'ui.py'))
WarningsTriageWindow = ui_module.WarningsTriageWindow

if __name__ == '__main__':
    win = WarningsTriageWindow(revit.doc)
    win.ShowDialog()
