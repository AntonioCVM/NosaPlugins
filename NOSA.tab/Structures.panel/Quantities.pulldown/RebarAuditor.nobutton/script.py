# -*- coding: utf-8 -*-
__title__   = "Rebar\nAuditor"
__version__ = "1.0"
__doc__     = """Rebar Auditor v1.0 — EC2

Rebar audit to Eurocode 2 (EN 1992-1-1):

  · Nominal cover vs. required cover by exposure class (Table 4.4N)
  · Minimum rebar ratio ρ_min by element type
  · Maximum rebar ratio ρ_max (EC2 §9)
  · Structural elements with no rebar assigned

Results by category with CSV export.
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
    def _lm(n, p):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('rebaraud_ui', os.path.join(lib_path, 'ui.py'))

launch_nosa_window(ui_module.RebarAuditorWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('rebarauditor')
except Exception:
    pass
