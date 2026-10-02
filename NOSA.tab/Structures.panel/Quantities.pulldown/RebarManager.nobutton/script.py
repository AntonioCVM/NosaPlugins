# -*- coding: utf-8 -*-
__title__   = "Rebar\nManager"
__version__ = "1.0"
__doc__     = "Rebar schedule export (BS 8666 format) and bar mark management across the whole model."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module('rebarmanager_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.RebarManagerWindow, revit.doc)
