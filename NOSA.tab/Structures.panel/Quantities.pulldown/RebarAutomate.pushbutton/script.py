# -*- coding: utf-8 -*-
__title__   = "Rebar\nAutomate"
__version__ = "0.1"
__doc__     = "Automatic reinforcement generation for structural hosts. Phase 4: footings live-fire test."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('rebarautomate_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.RebarAutomateWindow, revit.doc)
