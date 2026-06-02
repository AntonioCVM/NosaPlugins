# -*- coding: utf-8 -*-
__title__   = "Revision\nTracker"
__version__ = "1.0"
__doc__     = """Structural Revision Tracker v1.0

Saves snapshots of the structural model and computes deltas between them.

  Take Snapshot — records current elements + parameters to a JSON file.
  Compare Selected — shows Added / Removed / Changed elements vs saved snapshot.
  Select in Model — navigates to changed element.
  Export CSV — full delta report.

Ideal for tracking changes between design revisions or IFC submissions.
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

ui_module = _lm('revtrack_ui_local', os.path.join(lib_path, 'ui.py'))
RevisionTrackerWindow = ui_module.RevisionTrackerWindow

if __name__ == '__main__':
    win = RevisionTrackerWindow(revit.doc)
    win.ShowDialog()
