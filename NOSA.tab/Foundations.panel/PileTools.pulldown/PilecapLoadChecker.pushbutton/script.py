# -*- coding: utf-8 -*-
__title__   = "Pilecap\nGeometry Check"
__version__ = "1.1"
__doc__     = """Pilecap Geometry & Load Check v1.1

Checks geometric properties of pile cap elements and a partial load check:

  - Validates pile cap dimensions and layout
  - Reports geometric inconsistencies per pile cap
  - Reads N, Mx, My reactions from the analytical model where available
  - Pass/fail utilisation check is based on axial load (N) vs pile
    bearing capacity only — combined N+Mx+My utilisation and Vx/Vy shear
    checks are not yet implemented
  - Exports results to CSV
"""
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

from nosa_utils.base_window import launch_nosa_window

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
except (ImportError, AttributeError):
    def _lm(n, p):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('pilechk_ui', os.path.join(lib_path, 'ui.py'))

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('pilecaploadchecker')
except Exception:
    pass
launch_nosa_window(ui_module.PilecapLoadCheckerWindow, revit.doc)
