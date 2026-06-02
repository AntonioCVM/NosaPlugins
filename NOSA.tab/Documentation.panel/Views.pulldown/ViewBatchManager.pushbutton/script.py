# -*- coding: utf-8 -*-
__title__   = "View Batch\nManager"
__version__ = "1.0"
__doc__     = """View Batch Manager v1.0

Bulk operations on views:

  Rename Views tab:
    - Find & Replace names across all views
    - Add Prefix / Suffix
    - Case transform (Title / UPPER / lower / Sentence)
    - Live preview of new names before applying

  Apply Template tab:
    - Assign a view template to multiple views at once
    - Or remove an existing template assignment
"""
__author__ = "NOSA Engineering"

import sys, os

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

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

from pyrevit import revit

ui_module = _lm('viewbatchmanager_ui', os.path.join(lib_path, 'ui.py'))

if __name__ == '__main__':
    win = ui_module.ViewBatchManagerWindow(revit.doc)
    win.ShowDialog()
