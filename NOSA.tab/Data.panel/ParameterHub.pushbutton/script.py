# -*- coding: utf-8 -*-
__title__   = "Parameter\nHub"
__version__ = "1.0"
__doc__     = "Inspect and bulk-edit element parameters in one tool."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

from nosa_utils.bootstrap import load_module
_ui = load_module('parameterhub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.ParameterHubWindow, revit.doc)
