# -*- coding: utf-8 -*-
__title__   = "Issue\nWorkflow Hub"
__version__ = "1.0"
__doc__     = "Sheet issuance workflow — protocol check, pre-flight gate, revisions, package diff, and issue log, in one hub."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('issueworkflowhub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

win = _ui.IssueWorkflowHubWindow(revit.doc)
win.ShowDialog()

# Preserves IssueGate's original "proceed to export" handoff: closing the hub
# from the Issue Gate tab's Export button used to chain-launch ExportSheets.
# ExportSheets was retired to .nobutton this session, so this checks both
# suffixes — same dual-suffix pattern already used by AnnotationSuite's
# sibling-logic loader — to keep the handoff working regardless of which
# folder suffix the export tool currently has.
if getattr(win, 'proceed_to_export', False):
    _issue_dir = os.path.dirname(__file__)
    _exp_lib = None
    for _suffix in ('pushbutton', 'nobutton'):
        _candidate = os.path.abspath(os.path.join(_issue_dir, '..', 'ExportSheets.{}'.format(_suffix), 'lib'))
        if os.path.exists(os.path.join(_candidate, 'ui.py')):
            _exp_lib = _candidate
            break
    if _exp_lib:
        if _exp_lib not in sys.path:
            sys.path.insert(0, _exp_lib)
        _exp_ui = imp.load_source('exportsheets_ui_gate', os.path.join(_exp_lib, 'ui.py'))
        launch_nosa_window(_exp_ui.ExportSheetsProForm, revit.doc)
