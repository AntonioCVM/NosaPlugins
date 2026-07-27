# -*- coding: utf-8 -*-
__title__   = "Auto\nDimensions"
__version__ = "1.1"
__doc__     = "Auto-dimensioning hub — wall dimensions and GA grid dimensions with paper-constant offsets."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('annotationhub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.AnnotationHubWindow, revit.doc)
