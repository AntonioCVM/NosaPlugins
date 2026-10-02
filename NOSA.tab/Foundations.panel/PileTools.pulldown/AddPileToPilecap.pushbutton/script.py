# -*- coding: utf-8 -*-
__title__ = "Add Piling"
__version__ = "1.0"
__author__  = "A. Viñas"
__doc__ = """Places piles under a selected foundation slab and groups them.

Supports four pile arrangement patterns:
  · Rectangular — standard N×M grid aligned with slab span
  · Triangular   — offset rows for denser coverage
  · Hexagonal    — honeycomb layout (close-packed)
  · Manual       — pick each pile position by clicking in the model
"""

import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module(
    'addpiletopilecap_ui',
    os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

from pyrevit import revit, script

try:
    import nosa_utils.usage as _ut
    _ut.record('addpiletopilecap')
except Exception:
    pass

_ui.run(revit.doc, revit.uidoc, script.get_output())
