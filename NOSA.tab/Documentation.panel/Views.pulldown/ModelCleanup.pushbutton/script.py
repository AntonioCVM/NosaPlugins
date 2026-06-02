# -*- coding: utf-8 -*-
__title__   = "Model\nCleanup"
__version__ = "1.0"
__doc__     = """Model Cleanup Tool v1.0

Finds waste in the model to keep it lean and maintainable:

  Orphan Views    — views not placed on any sheet
  Unused Families — family types with zero placed instances
  Unused Templates — view templates assigned to no views
  Trivial Warnings — warnings unlikely to affect structural integrity

Results can be selected in model and exported to CSV.
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

ui_module = _lm('mcleanup_ui_local', os.path.join(lib_path, 'ui.py'))
ModelCleanupWindow = ui_module.ModelCleanupWindow

if __name__ == '__main__':
    win = ModelCleanupWindow(revit.doc)
    win.ShowDialog()
