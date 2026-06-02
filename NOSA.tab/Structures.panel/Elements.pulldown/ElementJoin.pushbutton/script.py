# -*- coding: utf-8 -*-
__title__   = "SmartJoin\nPro"
__version__ = "2.0"
__doc__     = """SmartJoin Pro v2.0

Priority-aware join system for structural elements.

Features:
  - Configurable priority order (Floors > Framing > Columns > Walls > Foundations)
  - Drag-reorder priority with persistence per project
  - Batch join with correct dominance order applied automatically
  - Fix existing joins with wrong dominance order
  - Manual pick mode: choose exactly which element cuts which
  - Scope: all elements or current selection
  - Select in model + Export CSV
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

ui_module = _lm('elemjoin_ui_local', os.path.join(lib_path, 'ui.py'))
ElementJoinWindow = ui_module.ElementJoinWindow

if __name__ == '__main__':
    win = ElementJoinWindow(revit.doc)
    win.ShowDialog()
