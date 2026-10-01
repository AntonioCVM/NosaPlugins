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
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from nosa_utils.base_window import launch_nosa_window

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
except (ImportError, AttributeError):
    def _lm(n, p):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p)
        sys.modules[n] = m
        return m

ui_module = _lm('annobatch_ui', os.path.join(lib_path, 'ui.py'))

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('annotationbatch')
except Exception:
    pass
launch_nosa_window(ui_module.AnnotationBatchWindow, revit.doc)
