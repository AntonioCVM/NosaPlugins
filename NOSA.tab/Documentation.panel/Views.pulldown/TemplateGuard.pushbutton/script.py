# -*- coding: utf-8 -*-
__title__   = "Template\nGuard"
__version__ = "1.0"
__doc__     = """Template Compliance Guard v1.0

Checks views and sheets against NOSA standards:
  - Views without template assigned
  - Non-standard scales
  - Sheet naming convention
  - Manual graphic overrides
  - Missing crop regions
  - Wrong detail level

Rules are configurable via rules.json (Edit Rules button).
Results can be exported to CSV and elements selected in model.
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

ui_module = _lm('tguard_ui_local', os.path.join(lib_path, 'ui.py'))
TemplateGuardWindow = ui_module.TemplateGuardWindow

if __name__ == '__main__':
    win = TemplateGuardWindow(revit.doc)
    win.ShowDialog()
