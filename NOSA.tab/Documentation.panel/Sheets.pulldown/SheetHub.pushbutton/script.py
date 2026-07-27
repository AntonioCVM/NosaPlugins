# -*- coding: utf-8 -*-
__title__   = "Sheet\nHub"
__version__ = "2.0"
__doc__     = "Unified sheet manager: NOSA protocol editing and sheet duplication."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

_ui = imp.load_source('sheethub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.SheetHubWindow, revit.doc, revit.uidoc)
