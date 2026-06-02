# -*- coding: utf-8 -*-
__title__   = "Annotation\nBatch"
__version__ = "1.0"
__doc__     = """Structural Annotation Batch v1.0

Batch-applies structural annotations to multiple views:

  Structural Tags tab:
    - Tag Structural Columns, Framing and Foundations
    - Skips already-tagged elements
    - Optional leader line

  Grid Bubbles tab:
    - Show or hide grid bubbles across selected views

Ideal for quickly annotating new or duplicated structural views.
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

ui_module = _lm('annobatch_ui_local', os.path.join(lib_path, 'ui.py'))
AnnotationBatchWindow = ui_module.AnnotationBatchWindow

if __name__ == '__main__':
    win = AnnotationBatchWindow(revit.doc)
    win.ShowDialog()
