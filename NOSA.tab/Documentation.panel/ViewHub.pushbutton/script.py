# -*- coding: utf-8 -*-
__title__   = "View\nHub"
__version__ = "1.0"
__doc__     = "View management, overrides and filters, view templates and view utilities in one hub."
__author__  = "A. Viñas"

import os, sys

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from nosa_utils.bootstrap import load_module
from nosa_utils.tabbed_hub import TabbedHub

_hub = load_module('view_hub_hub', os.path.join(os.path.dirname(__file__), 'lib', 'hub.py'))

from pyrevit import revit
launch_nosa_window(TabbedHub, u"View Hub", 'view_hub', _hub.tools(revit.doc, revit.uidoc))
