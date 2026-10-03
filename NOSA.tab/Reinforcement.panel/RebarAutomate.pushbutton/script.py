# -*- coding: utf-8 -*-
__title__   = "Rebar\nAutomate"
__doc__     = "Automatic reinforcement generation for structural hosts. Phase 4: footings live-fire test."
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

# PHASE F0 — migrated from imp.load_source to nosa_utils.bootstrap's
# unified loader. Registered name unchanged ('rebarautomate_ui').
_ui = load_module('rebarautomate_ui',
                   os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))

# PHASE F1 — single source of truth for the version string (deferred
# from F0). __version__ is read from here, not hand-typed, so the
# SAME number that shows in pyRevit's own button tooltip is also what
# NOSA_Rebar_Generator_Version stamps on every Rebar this plugin
# creates (see lib/_version.py, nosa_utils.shared_params.stamp_provenance).
_version_mod = load_module('rebarautomate_version',
                            os.path.join(os.path.dirname(__file__), 'lib', '_version.py'))
__version__ = _version_mod.RA_VERSION

launch_nosa_window_modeless(_ui.RebarAutomateWindow, revit.doc)
