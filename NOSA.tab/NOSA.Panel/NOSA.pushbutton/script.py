# -*- coding: utf-8 -*-
__title__   = "NOSA\nDashboard"
__version__ = "3.0"
__doc__     = "NOSA extension dashboard — version, environment, health checks and plugin index."
__author__  = "A. Viñas"

import os
import sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window

from nosa_utils.bootstrap import load_module
_ui = load_module('nosa_dashboard_ui',
                      os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

launch_nosa_window(_ui.NOSADashboardWindow)

# -- usage tracking --
try:
    import nosa_utils.usage as _ut
    _ut.record('nosa')
except Exception:
    pass
