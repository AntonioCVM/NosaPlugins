# -*- coding: utf-8 -*-
__title__ = "Align View\nTitles"
__doc__ = """Aligns view titles of viewports across sheets to match a reference.

FEATURES v3.0:
✓ Modern Interface
✓ Visual Preview
✓ Sheet Set Filtering
✓ Alignment Modes (Left/Center/Right)
"""
__author__  = "A. Viñas"
__version__ = "3.0"

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

ui_module = _lm('alignviewtitles_ui_local', os.path.join(lib_path, 'ui.py'))
AlignTitlesWindow = ui_module.AlignTitlesWindow

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('alignviewtitles')
except Exception:
    pass
launch_nosa_window(AlignTitlesWindow, revit.doc)
