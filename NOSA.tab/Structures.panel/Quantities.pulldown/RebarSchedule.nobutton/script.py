# -*- coding: utf-8 -*-
__title__   = "Rebar\nSchedule"
__version__ = "1.0"
__doc__     = """Rebar Schedule Generator v1.0

Produces a complete bar bending schedule from model rebar:

  · Groups by host element, diameter or shape code
  · Reads bar mark, shape, diameter, cut length and quantity
  · Calculates total length and weight (kg/t) per group
  · Phase and level filters to scope the schedule
  · Subtotals per group and grand total
  · Export to formatted Excel (BS 8666 style) or CSV
  · Select bars in model directly from the table

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
except (ImportError, AttributeError):
    def _lm(n, p):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p)
        sys.modules[n] = m
        return m

from pyrevit import revit

ui_module = _lm('rebar_schedule_ui', os.path.join(lib_path, 'ui.py'))

launch_nosa_window(ui_module.RebarScheduleWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('rebarschedule')
except Exception:
    pass
