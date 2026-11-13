# -*- coding: utf-8 -*-
__title__   = "Clash\nViewer"
__version__ = "1.0"
__doc__     = "Read a Navisworks clash report (.xlsm), browse its clashes and show the two elements in a dedicated 3D view."
__author__  = "A. Viñas"
# Modeless window: its ExternalEvent handlers must outlive this script run.
__persistentengine__ = True

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window_modeless
from nosa_utils.bootstrap import load_module
from pyrevit import revit

_ui = load_module('clashviewer_ui',
                  os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window_modeless(_ui.ClashViewerWindow, revit.doc)
