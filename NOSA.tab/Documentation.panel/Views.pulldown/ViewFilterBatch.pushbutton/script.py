# -*- coding: utf-8 -*-
__title__   = "Filter\nBatch"
__version__ = "1.0"
__doc__     = """ViewFilter Batch v1.0

Bulk-manage view filters across multiple views.

Features:
  - Copy all filters + graphic overrides from a source view to target views
  - Apply any project filter to multiple views at once
  - Batch enable / disable / remove filters in selected views
  - Filter and search views by name or view type
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

ui_module = _lm('viewfilterbatch_ui_local', os.path.join(lib_path, 'ui.py'))
ViewFilterBatchWindow = ui_module.ViewFilterBatchWindow

if __name__ == '__main__':
    win = ViewFilterBatchWindow(revit.doc)
    win.ShowDialog()
