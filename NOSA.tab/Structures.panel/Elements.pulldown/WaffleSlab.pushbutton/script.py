# -*- coding: utf-8 -*-
__title__ = "Waffle\nSlab"
__doc__ = """Creates waffle slab floors with real void openings and a compression layer.

Interactive UI for beam spacing, void depth, and slab thickness with multi-standard validation."""
__author__  = "A. Viñas"
__version__ = "2.2"

import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module(
    'waffleslab_ui',
    os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit, script

try:
    import nosa_utils.usage as _ut
    _ut.record('waffleslab')
except Exception:
    pass

_ui.run(revit.doc, revit.uidoc, script.get_output())
