# -*- coding: utf-8 -*-
__title__   = "Family\nAudit"
__version__ = "1.0"
__doc__     = """Family Audit v1.0

Inspect, audit and selectively purge Revit families.

Features:
  - Lists all loaded families with file size (MB), instance count
  - Flags unused families (0 instances) for easy cleanup
  - Shows parameter completeness score per family type
  - Selective purge: remove chosen unused families in one click
  - Search and filter by category or name
  - Export audit report to CSV
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

ui_module = _lm('familyaudit_ui_local', os.path.join(lib_path, 'ui.py'))
FamilyAuditWindow = ui_module.FamilyAuditWindow

if __name__ == '__main__':
    win = FamilyAuditWindow(revit.doc)
    win.ShowDialog()
