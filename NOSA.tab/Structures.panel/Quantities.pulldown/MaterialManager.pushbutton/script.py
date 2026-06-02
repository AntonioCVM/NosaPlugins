# -*- coding: utf-8 -*-
__title__   = "Material\nManager Pro"
__version__ = "2.0"
__doc__     = """Material Manager Pro v2.0

Audit, manage and assign materials across the model.

Features:
  - Lists all materials with usage count
  - Highlights unused materials and near-duplicate names
  - Search and filter by name or material class
  - Bulk delete unused materials
  - Elements tab: scan structural elements for material assignments
  - Detect missing materials and propose matches by keyword
  - Assign a material to multiple selected elements at once
  - Export both material and element reports to CSV
"""
__author__ = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('materialmanager_ui_local', os.path.join(lib_path, 'ui.py'))
MaterialManagerWindow = ui_module.MaterialManagerWindow

if __name__ == '__main__':
    win = MaterialManagerWindow(revit.doc)
    win.ShowDialog()
