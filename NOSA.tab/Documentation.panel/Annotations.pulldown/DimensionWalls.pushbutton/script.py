# -*- coding: utf-8 -*-
__title__ = "Dimension\nWalls"
__version__ = "8.0"
__doc__ = """Modernized Dimension Walls Tool.
Creates dimensions for straight and curved walls in plan views.
Supports Radius and Arc Length dimensions for curved walls.
"""
__author__ = "NOSA Extension"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), "lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('dimensionwalls_ui_local', os.path.join(lib_path, 'ui.py'))
DimensionWallsWindow = ui_module.DimensionWallsWindow

if __name__ == '__main__':
    window = DimensionWallsWindow(revit.doc)
    window.ShowDialog()
