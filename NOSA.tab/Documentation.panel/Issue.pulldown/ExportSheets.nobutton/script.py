# -*- coding: utf-8 -*-
__title__   = "Export\nSheets Pro"
__version__ = "4.2"
__doc__     = "Export project sheets to PDF, DWG, or DXF with NOSA naming and batch options."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_local_lib = os.path.join(os.path.dirname(__file__), 'lib')
if _local_lib not in sys.path:
    sys.path.insert(0, _local_lib)

from nosa_utils.base_window import launch_nosa_window

# ui.py's sibling modules (managers/utils/config/naming/exporters/
# validation/view_collector) are all named with an es_ prefix on disk
# specifically so they can never collide with another NOSA plugin's
# same-purpose file (Sheet Export Hub ships its own managers.py/utils.py/
# etc.) in pyRevit's cached-engine sys.modules across script runs in the
# same Revit session — the root cause of a previous "Cannot import name
# IssuePackageManager" failure here. No sys.modules purge needed with
# this naming scheme; the module names themselves are unique extension-wide.

try:
    _ui = imp.load_source('exportsheets_ui', os.path.join(_local_lib, 'ui.py'))
except Exception as _load_err:
    import traceback
    from pyrevit import forms
    forms.alert(
        u'Export Sheets Pro failed to load its module chain:\n{}\n\n{}'.format(
            _load_err, traceback.format_exc()),
        title=u'NOSA — Load Error')
    raise

from pyrevit import revit

launch_nosa_window(_ui.ExportSheetsProForm, revit.doc)
