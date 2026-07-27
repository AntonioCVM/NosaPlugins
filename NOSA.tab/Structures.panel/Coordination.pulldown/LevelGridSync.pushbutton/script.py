# -*- coding: utf-8 -*-
__title__   = "Level & Grid\nSync"
__version__ = "1.0"
__doc__     = """Level & Grid Sync v1.0

Compares levels and grids in the current structural model
against those in a linked Architecture / Reference model.

  - Levels with same name but different elevation
  - Grids renamed or missing in one of the models
  - New levels/grids present in the link but not in host
  - Tolerance configurable (default 1 mm)

Produces a discrepancy report for BIM coordination.
"""
__author__  = "A. Viñas"

import sys, os

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
except ImportError:
    import imp
    def _lm(n, p):
        return imp.load_source(n, p)

_ui = _lm('levelgridsync_ui', os.path.join(lib_path, 'ui.py'))

from pyrevit import revit

launch_nosa_window(_ui.LevelGridSyncWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('levelgridsync')
except Exception:
    pass
