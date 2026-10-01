# -*- coding: utf-8 -*-
__title__   = "Align Element\nto Column"
__version__ = "4.0"
__doc__     = "Aligns selected beams, ground beams or pilecaps to the centres of the selected columns."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

_ui = imp.load_source('centerbeam_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.CenterBeamToColumnWindow, revit.doc)
