# -*- coding: utf-8 -*-
__title__   = "Shared\nParameters"
__version__ = "1.0"
__doc__     = "Audits the project's shared parameter file against doc.ParameterBindings — flags orphaned bindings and GUID conflicts. Read-only."
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit

_ui = imp.load_source('sharedparammanager_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.SharedParamManagerWindow, revit.doc)
