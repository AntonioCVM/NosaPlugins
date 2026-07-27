# -*- coding: utf-8 -*-
__title__   = "Type\nRenamer"
__version__ = "1.0"
__doc__     = "Batch-rename element types by category — find & replace or prefix/suffix."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('typerenamer_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.TypeRenamerWindow, revit.doc)
