# -*- coding: utf-8 -*-
__title__   = "Sheet\nNamer"
__version__ = "2.2"
__doc__     = "Bulk sheet renaming with NOSA protocol suggestions."
__author__  = "A. Viñas"

import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module(
    'sheetnamer_ui',
    os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit

try:
    import nosa_utils.usage as _ut
    _ut.record('sheetnamer')
except Exception:
    pass

launch_nosa_window(_ui.SheetNamerWindow, revit.doc, revit.uidoc)
