# -*- coding: utf-8 -*-
__title__ = "Clash\nReport"
__version__ = "2.0"
__doc__ = """Detects geometric clashes between elements of selected categories.

FEATURES v2.0:
✓ Modern WPF Interface
✓ Real-time Clash Analysis
✓ Isolate Clashing Elements
✓ Export HTML Reports
"""
__author__ = "Antonio Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('clashreport_ui_local', os.path.join(lib_path, 'ui.py'))
ClashReportWindow = ui_module.ClashReportWindow

# Run
if __name__ == '__main__':
    window = ClashReportWindow(revit.doc)
    window.ShowDialog()
