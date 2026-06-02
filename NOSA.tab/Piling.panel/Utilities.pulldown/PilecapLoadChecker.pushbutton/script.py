# -*- coding: utf-8 -*-
__title__   = "Pilecap\nChecker"
__version__ = "1.0"
__doc__     = """Pilecap Load Checker v1.0

Applies geometric rule checks to all pilecaps in the model.

Rules (BS 8004 / EC7):
  - Minimum pile spacing: 3× pile diameter
  - Minimum edge distance: 1.5× pile diameter
  - Minimum cap depth: 600 mm
  - Maximum aspect ratio: 2.5

Highlights failing pilecaps and selects them in model.
Export results to CSV.
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

ui_module = _lm('pilechk_ui_local', os.path.join(lib_path, 'ui.py'))
PilecapLoadCheckerWindow = ui_module.PilecapLoadCheckerWindow

if __name__ == '__main__':
    win = PilecapLoadCheckerWindow(revit.doc)
    win.ShowDialog()
