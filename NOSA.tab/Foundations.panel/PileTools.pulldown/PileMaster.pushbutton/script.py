# -*- coding: utf-8 -*-
"""
PileMaster: Consolidated Piling Tools
"""
__title__   = "Pile\nMaster"
__version__ = "2.1"
__doc__     = "Consolidated piling tools: coordinate export, pile numbering, and sheet layout for foundation surveys."
__author__  = "A. Viñas"

import sys, os

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
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
    except (ImportError, AttributeError):
        from nosa_utils.bootstrap import load_module
        m = load_module(n, p); sys.modules[n] = m; return m

_lm('pilemaster_logic_coords_local',    os.path.join(lib_path, 'logic_coords.py'))
_lm('pilemaster_logic_numbering_local', os.path.join(lib_path, 'logic_numbering.py'))
_lm('pilemaster_logic_sheets_local',    os.path.join(lib_path, 'logic_sheets.py'))

ui_module = _lm('pilemaster_ui_local', os.path.join(lib_path, 'ui.py'))
PileMasterWindow = ui_module.PileMasterWindow

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('pilemaster')
except Exception:
    pass
launch_nosa_window(PileMasterWindow)

