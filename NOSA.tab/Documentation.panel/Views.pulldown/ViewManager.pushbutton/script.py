# -*- coding: utf-8 -*-
__title__   = "View\nManager"
__version__ = "1.0"
__doc__     = """View Manager v1.0

Full batch view management suite:

  • Create — plan views from levels × view family type,
    name pattern, template and scale applied on creation
  • Duplicate — batch duplicate (plain / with detailing / as dependent)
    with automatic renaming
  • Rename — find & replace, prefix/suffix, case transform, live preview
  • Templates — assign or remove view templates in bulk
  • Clean — find views not placed on any sheet and delete selected
"""
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('viewmanager_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.ViewManagerWindow, revit.doc)
