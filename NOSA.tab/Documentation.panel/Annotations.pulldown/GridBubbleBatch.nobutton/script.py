# -*- coding: utf-8 -*-
__title__   = "Grid Bubble\nBatch"
__version__ = "1.0"
__doc__     = "Batch show, hide, or standardise grid bubbles across views."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module('gridbubblebatch_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit
launch_nosa_window(_ui.GridBubbleBatchWindow, revit.doc)

try:
    import nosa_utils.usage as _ut
    _ut.record('gridbubblebatch')
except Exception:
    pass
