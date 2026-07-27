# -*- coding: utf-8 -*-
__title__   = "GA Auto\nDimension"
__version__ = "1.1"
__doc__     = """GA Auto-Dimension v1.1

Automatic dimensioning for structural GA floor plans:

  Module 1 — Off-grid elements
    · Detects columns and foundations whose centre does not coincide
      with a gridline (within a configurable tolerance)
    · Creates horizontal and vertical dimensions to the nearest grid

  Module 2 — Walls
    · Wall length dimension (end to end)
    · Perpendicular dimension from wall to nearest gridline

  Module 3 — Slab corners
    · Detects vertices of slab boundary edges
    · Creates dimensions from each corner to the nearest
      H and V gridlines

  Module 4 — Grid spacing chains
    · Continuous dimension chains across all H and V gridlines

Dimension line offset is constant on paper (default 8 mm) and
scales automatically with the view scale.

Works on the active floor plan view.
"""
__author__  = "A. Viñas"

import os, sys, imp

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import launch_nosa_window
from pyrevit import revit, forms
from Autodesk.Revit import DB

view = revit.uidoc.ActiveView
if not isinstance(view, DB.ViewPlan):
    forms.alert(u'GA Auto-Dimension requires an active floor plan view.\n'
                u'Activate a floor plan and run again.',
                title=u'Invalid view')
else:
    _ui = imp.load_source('gadim_ui',
                          os.path.join(os.path.dirname(__file__), 'lib', 'ui.py'))
    launch_nosa_window(_ui.GAAutoDimWindow, revit.doc, view)
