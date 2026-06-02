# -*- coding: utf-8 -*-
__title__   = "NOSA\nDashboard"
__version__ = "3.0"
__doc__     = "NOSA extension dashboard — version, environment, health checks and plugin index."
__author__  = "Antonio Viñas"

import os
import sys
import imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

_ui = imp.load_source('nosa_dashboard_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

win = _ui.NOSADashboardWindow()
win.ShowDialog()
