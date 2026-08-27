# -*- coding: utf-8 -*-
__title__   = "Rebar\nAutomate"
__version__ = "0.1"
__doc__     = "Automatic reinforcement generation for structural hosts. Phase 4: footings live-fire test."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from nosa_utils.bootstrap import load_module
from pyrevit import revit

# PHASE F0 — migrated from imp.load_source to nosa_utils.bootstrap's
# unified loader. Registered name unchanged ('rebarautomate_ui').
_ui = load_module('rebarautomate_ui',
                   os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.RebarAutomateWindow, revit.doc)
