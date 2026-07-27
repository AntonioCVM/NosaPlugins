# -*- coding: utf-8 -*-
__title__   = "Text\nTools"
__version__ = "1.0"
__doc__     = "Batch rename elements and convert text case in one tool."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('texttools_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.TextToolsWindow, revit.doc)
