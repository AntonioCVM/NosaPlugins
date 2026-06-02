# -*- coding: utf-8 -*-
__title__   = "Quantification\nQA"
__version__ = "1.0"
__doc__     = """Concrete & Steel Quantification QA v1.0

Extracts quantities from the structural model and runs QA checks:

Quantities tab:
  - Volume (m³) and area (m²) per category and level
  - Subtotals and grand totals

Rebar tab:
  - Bar count and total length by diameter and level

QA Issues tab:
  - Elements without material (High)
  - Zero-volume elements (Medium)
  - Volume outliers by category (Medium)

Export all tabs to CSV with a single click.
"""
__author__ = "NOSA Engineering"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path: sys.path.insert(0, lib_path)

def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        import imp; m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('quantqa_ui_local', os.path.join(lib_path, 'ui.py'))
QuantificationQAWindow = ui_module.QuantificationQAWindow

if __name__ == '__main__':
    win = QuantificationQAWindow(revit.doc)
    win.ShowDialog()
