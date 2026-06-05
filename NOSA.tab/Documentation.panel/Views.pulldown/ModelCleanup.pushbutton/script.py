# -*- coding: utf-8 -*-
__title__   = "Model\nCleanup"
__version__ = "1.0"
__doc__     = """Model Cleanup v1.0

Identifies and removes unused elements:

  - Orphaned 2D elements (lines, text)
  - Unused imported families
  - View templates not assigned to any view
  - Revit warnings summary

Helps keep the model lean before issue.
"""
__author__  = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
except (ImportError, AttributeError):
    import imp
    def _lm(n, p):
        m = imp.load_source(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('mcleanup_ui', os.path.join(lib_path, 'ui.py'))

if __name__ == '__main__':
    win = ui_module.ModelCleanupWindow(revit.doc)
    win.ShowDialog()
