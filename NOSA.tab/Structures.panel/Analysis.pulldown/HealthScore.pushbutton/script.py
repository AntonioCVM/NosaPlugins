# -*- coding: utf-8 -*-
__title__   = "Health\nScore"
__version__ = "1.0"
__doc__     = """Structural Model Health Score v1.0

Runs a set of structural QA checks and returns a weighted score 0-100.

Checks:
  - Elements without material
  - Analytical model disabled
  - Orphan foundations (no column above)
  - Model warnings
  - Missing Mark parameter
  - Excessive level offsets

Results can be exported to CSV and elements can be selected in the model.
"""
__author__  = "NOSA Engineering"

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

ui_module = _lm('healthscore_ui_local', os.path.join(lib_path, 'ui.py'))
HealthScoreWindow = ui_module.HealthScoreWindow

if __name__ == '__main__':
    win = HealthScoreWindow(revit.doc)
    win.ShowDialog()
