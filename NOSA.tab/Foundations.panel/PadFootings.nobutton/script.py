# -*- coding: utf-8 -*-
__title__   = "Pad\nFootings"
__version__ = "1.0"
__doc__     = "Batch-create isolated pad footings under selected structural columns."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('padfootings_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.PadFootingsWindow, revit.doc)
