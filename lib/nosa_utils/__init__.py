# -*- coding: utf-8 -*-
"""
NOSA Utils — shared utility library for the NOSA pyRevit Extension.

Submodules are imported directly by consumers (e.g. `from nosa_utils.theme
import ThemeManager`), never via this package's __init__ — so it does not
import them here. Several submodules touch the Revit API or pyrevit.forms
at module level, and eagerly importing all of them on every
`from nosa_utils.X import Y` would pull that in as a side effect regardless
of which submodule was actually needed.
"""

__version__ = "2.0.0"
__author__  = "A. Viñas"
