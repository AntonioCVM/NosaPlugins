# -*- coding: utf-8 -*-
__title__   = "View Batch\nManager"
__version__ = "1.0"
__doc__     = """View Batch Manager v1.0

Bulk operations on views:

  Rename Views tab:
    - Find & Replace names across all views
    - Add Prefix / Suffix
    - Case transform (Title / UPPER / lower / Sentence)
    - Live preview of new names before applying

  Apply Template tab:
    - Assign a view template to multiple views at once
    - Or remove an existing template assignment
"""
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

_ui = imp.load_source('viewbatchmanager_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit

launch_nosa_window(_ui.ViewBatchManagerWindow, revit.doc)

try:
    import nosa_utils.usage as _ut
    _ut.record('viewbatchmanager')
except Exception:
    pass
