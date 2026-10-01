# -*- coding: utf-8 -*-
__title__   = "Template\nGuard"
__version__ = "1.0"
__doc__     = """Template Guard v1.0

Enforces view template rules across the project:

  - Detects views without an assigned template
  - Checks required parameters are set
  - Flags deviations from the defined standard

Run before issue to validate view discipline compliance.
"""
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

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

ui_module = _lm('tguard_ui', os.path.join(lib_path, 'ui.py'))

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('templateguard')
except Exception:
    pass
launch_nosa_window(ui_module.TemplateGuardWindow, revit.doc)
