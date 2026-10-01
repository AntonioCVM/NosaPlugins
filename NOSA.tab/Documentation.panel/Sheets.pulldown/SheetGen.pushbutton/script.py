# -*- coding: utf-8 -*-
__title__   = "Sheet\nGen"
__version__ = "3.0"
__doc__     = """Sheet Gen v3.0

Full bulk sheet production suite:

  • Edit Sheets — cell edits + Apply Changes
  • Create / Clone — type rows, add multiple blanks, CREATE SHEETS
  • Sidebar clone — duplicate a source sheet N times
  • Duplicate selected — layouts + duplicated model views
  • Send to Create grid — copy NOSA metadata, new blank sheets
  • Renumber — prefix / start / step / suffix / padding
  • Import from CSV or Excel (create or update sheets)
  • Export sheet list to CSV or Excel (round-trip editing)
"""
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

from nosa_utils.bootstrap import load_module
_ui = load_module('sheetgen_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.SheetComposerWindow, revit.doc)
