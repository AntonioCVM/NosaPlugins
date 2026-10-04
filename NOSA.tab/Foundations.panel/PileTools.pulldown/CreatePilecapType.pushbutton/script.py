# -*- coding: utf-8 -*-
__title__   = "Create\nPilecap"
__version__ = "3.0"
__doc__     = """Create Pile Cap v3.0

Design a pile cap assembly in the NOSA interface:
  - Set pile grid (H × V), spacing, edge clearance, cutoff
  - Select pile type, cap slab type, and level
  - Visual schematic preview updates live
  - Click PLACE PILE CAP, then click in the model to set the centre

Creates: one cap slab (Foundation Slab FloorType when available) + n_h × n_v piles (Structural Foundations).
"""
__author__  = "A. Viñas"

import sys, os

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

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

from pyrevit import revit

ui_module = _lm('createpilecap_ui', os.path.join(lib_path, 'ui.py'))

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('createpilecaptype')
except Exception:  # nosa-lint: disable=NOSA006 - usage stats must never break the tool
    pass
launch_nosa_window(ui_module.CreatePilecapWindow, revit.doc)
