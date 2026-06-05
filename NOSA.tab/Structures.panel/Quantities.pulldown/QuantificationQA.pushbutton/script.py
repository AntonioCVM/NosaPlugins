# -*- coding: utf-8 -*-
__title__   = "Quantification\nQA"
__version__ = "1.0"
__doc__     = """Quantification QA v1.0

Quality-checks structural quantity takeoffs:

  - Compares scheduled quantities against geometry
  - Detects duplicate elements affecting schedules
  - Flags zero-length or zero-area elements
  - Validates material assignments
  - Exports QA report to CSV
"""
__author__  = "NOSA Engineering"

import sys, os
from pyrevit import revit

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

ui_module = _lm('quantqa_ui', os.path.join(lib_path, 'ui.py'))

if __name__ == '__main__':
    win = ui_module.QuantificationQAWindow(revit.doc)
    win.ShowDialog()
