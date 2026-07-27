# -*- coding: utf-8 -*-
__title__   = "Missing\nRebar"
__version__ = "1.0"
__doc__     = "Find structural elements with no rebar assigned. Summary by category with coverage percentage. CSV export."
__author__  = "A. Viñas"

import os, sys, imp

# Pulldown pushbutton: 4×'..'
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('rebarcoverageqa_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.RebarCoverageWindow, revit.doc)
