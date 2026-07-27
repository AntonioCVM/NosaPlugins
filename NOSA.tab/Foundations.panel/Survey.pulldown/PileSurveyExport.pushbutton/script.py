# -*- coding: utf-8 -*-
__title__   = "Pile Survey\nExport"
__version__ = "1.0"
__doc__     = """Pile Survey Export v1.0

Exports coordinates of all piles in the model in formats
ready for surveying / setting out on site:

  · X, Y, Z of the pile head and toe
  · Mark, type, diameter and length
  · Inclination and azimuth (for raking piles)
  · CSV export (compatible with Leica, Trimble, AutoCAD)
  · Excel export with NOSA formatting
  · Comparison against construction tolerances

Reads piles modelled as Structural Columns or Structural Framing
with the parameter 'NOSA_IsPile'=1 or whose family name contains
'pile', 'pilote' or 'pila'.
"""
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from nosa_utils.base_window import launch_nosa_window

_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
except (ImportError, AttributeError):
    import imp
    def _lm(n, p):
        m = imp.load_source(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('pilesurvey_ui', os.path.join(lib_path, 'ui.py'))

launch_nosa_window(ui_module.PileSurveyWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('pilesurveyexport')
except Exception:
    pass
