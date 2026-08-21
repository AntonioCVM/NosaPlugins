# -*- coding: utf-8 -*-
__title__   = "Survey\nLayout"
__version__ = "1.1"
__doc__     = """Survey Layout Table v1.1

Generates a survey coordinate table for structural elements:

  · Columns, piles, pile caps and isolated foundations
  · X, Y, Z coordinates in project reference system
  · Mark, level, type and material for each element
  · Automatic pile/pile cap detection by family name and geometry
  · Export to Excel and CSV (Leica/Trimble compatible)
  · Select elements in model from the table

Useful for transferring coordinates to site survey and setting out.
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

ui_module = _lm('replanteo_ui', os.path.join(lib_path, 'ui.py'))

launch_nosa_window(ui_module.CuadroReplanteoWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('cuadroreplanteo')
except Exception:
    pass
