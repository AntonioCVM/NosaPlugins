# -*- coding: utf-8 -*-
__title__   = "Health\nScore"
__version__ = "1.0"
__doc__     = """Model Health Score v1.0

Produces a composite score (0-100) from multiple quality checks:

  - Warning count and severity
  - Family parameter completeness
  - View template compliance
  - Unused element ratio
  - Revision currency

Score is logged over time to track model quality trends.
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
    import imp
    def _lm(n, p):
        m = imp.load_source(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('healthscore_ui', os.path.join(lib_path, 'ui.py'))

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('healthscore')
except Exception:
    pass
launch_nosa_window(ui_module.HealthScoreWindow, revit.doc)
