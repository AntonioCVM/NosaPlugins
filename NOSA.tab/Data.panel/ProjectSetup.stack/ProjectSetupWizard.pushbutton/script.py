# -*- coding: utf-8 -*-
__title__   = "Project\nSetup"
__version__ = "1.0"
__doc__     = """Project Setup Wizard v1.0

One-click project configuration for NOSA Engineering projects.

  · Sets project information (client, code, site address, project number)
  · Creates NOSA standard worksets (Structure, Architecture, MEP, Shared Levels & Grids, Links)
  · Applies NOSA project parameters (shared parameters)
  · Creates standard levels if none exist
  · Creates title block sheets (Cover + Drawing Index)
  · Optionally loads NOSA title block and standard families

Select the steps to run, then click Configure.
"""
__author__  = "A. Viñas"

import sys, os
from pyrevit import revit

lib_path = os.path.join(os.path.dirname(__file__), 'lib')
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

from nosa_utils.base_window import launch_nosa_window

_ext_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

try:
    import importlib.util as _iu
    def _lm(n, p):
        s = _iu.spec_from_file_location(n, p); m = _iu.module_from_spec(s)
        sys.modules[n] = m; s.loader.exec_module(m); return m
except (ImportError, AttributeError):
    import imp
    def _lm(n, p):
        m = imp.load_source(n, p); sys.modules[n] = m; return m

ui_module = _lm('projsetup_ui', os.path.join(lib_path, 'ui.py'))

launch_nosa_window(ui_module.ProjectSetupWindow, revit.doc)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('projectsetupwizard')
except Exception:
    pass
