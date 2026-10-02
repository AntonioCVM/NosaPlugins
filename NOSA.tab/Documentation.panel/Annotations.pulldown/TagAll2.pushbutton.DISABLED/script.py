# -*- coding: utf-8 -*-
__title__ = "Tag All"
__doc__ = """Batch tag multiple categories across multiple views.

FEATURES v3.1:
✓ Modern Interface
✓ Configuration Dashboard
✓ Batch View Selection
✓ Skip Duplicates
"""
__author__  = "A. Viñas"
__version__ = "3.1"

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
        from nosa_utils.bootstrap import load_module
        import imp; m = load_module(n, p); sys.modules[n] = m; return m

ui_module = _lm('tagall_ui_local', os.path.join(lib_path, 'ui.py'))
TagAllWindow = ui_module.TagAllWindow

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('tagall')
except Exception:
    pass
launch_nosa_window(TagAllWindow, revit.doc)
