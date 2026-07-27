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
_ui = imp.load_source('exportsheets_ui', os.path.join(_local_lib, 'ui.py'))

from pyrevit import revit

launch_nosa_window(_ui.ExportSheetsProForm, revit.doc)
