# -*- coding: utf-8 -*-
__title__   = "Bay\nSections"
__version__ = "1.0"
__doc__     = "Auto-generate structural section and elevation views for selected grid intersections or bays."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

_ui = imp.load_source('baysections_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.BaySectionsWindow, revit.doc, revit.uidoc)
