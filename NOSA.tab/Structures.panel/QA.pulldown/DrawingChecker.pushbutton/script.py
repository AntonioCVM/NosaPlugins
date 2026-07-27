# -*- coding: utf-8 -*-
__title__   = "Drawing\nChecker"
__version__ = "1.0"
__doc__     = "Pre-emission quality checks for structural drawings — levels, scale consistency, tags, warnings and view templates."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
_ui = imp.load_source('drawingchecker_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.DrawingCheckerWindow, revit.doc)

try:
    import nosa_utils.usage as _ut
    _ut.record('drawingchecker')
except Exception:
    pass
