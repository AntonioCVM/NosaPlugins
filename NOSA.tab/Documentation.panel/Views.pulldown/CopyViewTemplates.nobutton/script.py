# -*- coding: utf-8 -*-
__title__ = "Copy View\nTemplates"
__version__ = "2.0"
__doc__ = """Modernized Copy View Templates Tool.
Copies view template settings or manual overrides from one view to multiple destination views.
"""
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from nosa_utils.base_window import launch_nosa_window

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('copyviewtemplates_ui_local', os.path.join(lib_path, 'ui.py'))
CopyTemplatesWindow = ui_module.CopyTemplatesWindow

launch_nosa_window(CopyTemplatesWindow, revit.doc)
# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('copyviewtemplates')
except Exception:
    pass
