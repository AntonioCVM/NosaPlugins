# -*- coding: utf-8 -*-
"""Bar location codes for the label (B1/B2/T1/T2) and FreeForm cut-length rounding."""
from __future__ import print_function
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))

import rebar_batch
import rebar_bending


def check(label, condition):
    assert condition, label
    print(label + ': OK')


check('mats map to B1/B2/T1/T2',
      [rebar_batch.location_code(l) for l in ('bottom_x', 'bottom_y', 'top_x', 'top_y')]
      == ['B1', 'B2', 'T1', 'T2'])
check('U-bars, walls and unknown layers get no code',
      all(rebar_batch.location_code(l) == '' for l in ('closure_x', 'vertical', 'stirrup', None)))
check('FreeForm length rounds up to 25 mm like a Set',
      rebar_bending.round_length_mm(2288.54, 25.0, 'Up') == 2300.0)
check('an exact multiple is not pushed up a step',
      rebar_bending.round_length_mm(2300.0000001, 25.0, 'Up') == 2300.0)
check('Down and nearest rounding',
      rebar_bending.round_length_mm(2288.5, 5.0, 'Down') == 2285.0
      and rebar_bending.round_length_mm(2288.5, 25.0, 'Nearest') == 2300.0)
check('no rounding step leaves the length alone',
      rebar_bending.round_length_mm(2288.5, 0, 'Up') == 2288.5)
print('\nALL LOCATION / LENGTH ROUNDING CHECKS PASSED')

import types
_autodesk = types.ModuleType('Autodesk'); _revit = types.ModuleType('Autodesk.Revit')
_revit.DB = types.ModuleType('Autodesk.Revit.DB'); _autodesk.Revit = _revit
sys.modules.setdefault('Autodesk', _autodesk); sys.modules.setdefault('Autodesk.Revit', _revit)
sys.modules.setdefault('Autodesk.Revit.DB', _revit.DB)
import rebar_detailing as rd
check('sections and details get Mark only',
      all(rd.label_kind_for_view_type(v) == 'Mark only' for v in ('Section', 'Detail')))
check('plans and elevations get the full label',
      all(rd.label_kind_for_view_type(v) == 'Full label' for v in ('FloorPlan', 'Elevation', 'CeilingPlan')))
check('swapping keeps the leader end', rd.swap_label_kind('Full label - Arrow', 'Mark only') == 'Mark only - Arrow'
      and rd.swap_label_kind('Mark only - Dot', 'Full label') == 'Full label - Dot')
check('a non-NOSA tag type is left alone', rd.swap_label_kind('Rebar Tag 1', 'Mark only') is None)
print('\nALL TAG TYPE CHECKS PASSED')
