# -*- coding: utf-8 -*-
__title__   = "Issue\nGate"
__version__ = "1.0"
__doc__     = "Pre-flight Go/No-Go checks before sheet issue — protocol, revisions, title block and duplicates."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
_ui = imp.load_source('issuegate_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
win = _ui.IssueGateWindow(revit.doc)
win.ShowDialog()

if getattr(win, 'proceed_to_export', False):
    _exp_lib = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'ExportSheets.pushbutton', 'lib'))
    if _exp_lib not in sys.path:
        sys.path.insert(0, _exp_lib)
    _exp_ui = imp.load_source('exportsheets_ui_gate', os.path.join(_exp_lib, 'ui.py'))
    launch_nosa_window(_exp_ui.ExportSheetsProForm, revit.doc)

try:
    import nosa_utils.usage as _ut
    _ut.record('issuegate')
except Exception:
    pass
