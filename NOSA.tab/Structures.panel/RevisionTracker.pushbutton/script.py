# -*- coding: utf-8 -*-
__title__   = "Revision\nTracker"
__version__ = "1.0"
__doc__     = """Revision Tracker v1.0

Tracks and manages sheet revisions across the project:

  - Lists all sheets with their current revision status
  - Bulk-assign revisions to selected sheets
  - Filter by revision sequence or sheet set
  - Export revision schedule to CSV
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

ui_module = _lm('revtrack_ui', os.path.join(lib_path, 'ui.py'))

if __name__ == '__main__':
    win = ui_module.RevisionTrackerWindow(revit.doc)
    win.ShowDialog()
