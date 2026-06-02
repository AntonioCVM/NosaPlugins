# -*- coding: utf-8 -*-
__title__   = "Sheet\nComposer"
__version__ = "2.1"
__doc__     = """Sheet Composer v2.1

Bulk sheet workflow without requiring CSV:

  • Edit Sheets — cell edits + Apply Changes
  • Create / Clone — type rows, add multiple blanks, CREATE SHEETS
  • Sidebar clone — duplicate a source sheet N times
  • Duplicate selected — from Edit grid (layouts + duplicated model views)
  • Send to Create grid — copy NOSA metadata, new blank sheets

CSV import stays optional.

Also: renumber, parameter sync on new sheets (incl. Form).
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

ui_module = _lm('sheetcomposer_ui_local', os.path.join(lib_path, 'ui.py'))
SheetComposerWindow = ui_module.SheetComposerWindow

if __name__ == '__main__':
    win = SheetComposerWindow(revit.doc)
    win.ShowDialog()
