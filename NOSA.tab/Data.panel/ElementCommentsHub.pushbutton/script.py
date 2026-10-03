# -*- coding: utf-8 -*-
__title__   = "Element\nComments"
__version__ = "1.0"
__doc__     = "Assigns a shared Comments code per exact Family+Type across structural elements (beams, columns, foundations, floors, walls), manually or automatically."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module('elementcommentshub_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit

try:
    import nosa_utils.usage as _ut
    _ut.record('element_comments_hub')
except Exception:
    pass

launch_nosa_window(_ui.ElementCommentsHubWindow, revit.doc, revit.uidoc)
