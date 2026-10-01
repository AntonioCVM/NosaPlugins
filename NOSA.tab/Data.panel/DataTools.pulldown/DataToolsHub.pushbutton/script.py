# -*- coding: utf-8 -*-
__title__   = "Data\nTools"
__version__ = "1.0"
__doc__     = """Data Tools Hub v1.0

Single sidebar-navigation hub consolidating:
  - Excel Sync        (import/export CSV & Excel <-> Revit parameters)
  - Workset Health     (audit worksets, move elements between worksets)
  - Model Cleanup      (find & purge orphan views, unused families/templates,
                        CAD imports, unplaced rooms, trivial warnings)
  - Link Manager       (RVT link / CAD import status, reload, unload, remove)
  - Type Renamer       (batch-rename element types by category)
"""
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

from nosa_utils.bootstrap import load_module
_ui = load_module('datatoolshub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.DataToolsHubWindow, revit.doc)
