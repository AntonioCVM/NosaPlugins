# -*- coding: utf-8 -*-
__title__   = "View\nUtilities"
__version__ = "1.0"
__doc__     = ("Align view titles, generate bay sections, navigate levels, "
               "explore view dependencies, and quick-apply halftone / "
               "section-box actions — all in one hub.")
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module('viewutilities_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit

launch_nosa_window(_ui.ViewUtilitiesWindow, revit.doc, revit.uidoc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('viewutilities')
except Exception:  # nosa-lint: disable=NOSA006 - usage stats must never break the tool
    pass
