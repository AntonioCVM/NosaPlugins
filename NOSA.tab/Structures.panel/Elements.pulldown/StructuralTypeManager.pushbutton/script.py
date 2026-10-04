# -*- coding: utf-8 -*-
__title__ = "Structural\nTypes"
__version__ = "2.0"
__doc__ = """Structural Type Manager v2.0

ElementTypes per category: optional Revit selection, presets,
parameter scope + substring filters, Aux read-only column,
unit-aware numeric writes, DUPLICATE, dry-run previews, CSV, logging."""
__author__  = "A. Viñas"

import sys
import os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)
_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

from nosa_utils.base_window import launch_nosa_window


def _lm(n, p):
    try:
        import importlib.util as _iu
        s = _iu.spec_from_file_location(n, p)
        m = _iu.module_from_spec(s)
        sys.modules[n] = m
        s.loader.exec_module(m)
        return m
    except (ImportError, AttributeError):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p)
        sys.modules[n] = m
        return m


ui_module = _lm(
    'struct_type_mgr_ui_local',
    os.path.join(lib_path, 'ui.py'))
StructuralTypeManagerWindow = ui_module.StructuralTypeManagerWindow


# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('structuraltypemanager')
except Exception:  # nosa-lint: disable=NOSA006 - usage stats must never break the tool
    pass
launch_nosa_window(StructuralTypeManagerWindow, revit.doc, getattr(revit, 'uidoc', None))
