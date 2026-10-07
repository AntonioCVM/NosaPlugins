# -*- coding: utf-8 -*-
"""Bar location codes for the label (B1/B2/T1/T2) and FreeForm cut-length rounding."""
from __future__ import print_function
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'lib'))

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

import wall_rebar as wr
check('the face with the slab beside it is N, the other F',
      wr.face_codes([True, False], [False, True]) == ['N', 'F']
      and wr.face_codes([False, True], [False, True]) == ['F', 'N'])
check('no slab on either side: Revit exterior side is F',
      wr.face_codes([False, False], [True, False]) == ['F', 'N'])
check('slab on both sides: Revit exterior side is F',
      wr.face_codes([True, True], [False, True]) == ['N', 'F'])
check('a single face beside a slab is N, a lone outer face F',
      wr.face_codes([True], [True]) == ['N'] and wr.face_codes([False], [True]) == ['F'])
check('SMDSC 4.2.1 layer codes: N1/N2 near face, F1/F2 far face, 1 = outer layer',
      wr.layer_code('N', True) == 'N1' and wr.layer_code('F', False) == 'F2'
      and wr.layer_code(None, True) is None)
print('\nALL WALL FACE CHECKS PASSED')

import rebar_marking as rm
check('mark numbers read back from the mark itself',
      rm.mark_number('05') == 5 and rm.mark_number('05B') == 5 and rm.mark_number('112') == 112
      and rm.mark_number('') == 0 and rm.mark_number(None) == 0)
print('\nALL MARK NUMBER CHECKS PASSED')

pos = wr._evenly_spaced_mm(5000, 200, 50)
check('wall bars exactly at the spacing asked for, centred',
      all(abs((b - a) - 200.0) < 1e-6 for a, b in zip(pos[:-1], pos[1:]))
      and abs((pos[0] - 50) - (4950 - pos[-1])) < 1e-6)
check('a separate top clearance keeps the bars inside it',
      wr._evenly_spaced_mm(3000, 200, 50, 70)[-1] <= 2930 and wr._evenly_spaced_mm(3000, 200, 50, 70)[0] >= 50)
u = wr.top_ubar_positions_mm([50.0, 250.0, 450.0], 500.0, 12.0, 10.0, 50.0)
check('one coronation U-bar beside each vertical, the last turned back inside the wall',
      u == [61.0, 261.0, 439.0])
check('equal steps make one run, a change of step starts another',
      wr.uniform_runs_mm([61.0, 261.0, 439.0]) == [[61.0, 261.0], [439.0]]
      and wr.uniform_runs_mm([0.0, 100.0, 200.0]) == [[0.0, 100.0, 200.0]])
print('\nALL WALL U-BAR CHECKS PASSED')

lo, hi = wr._trim_to_step_mm(50.0, 2812.0)
check('a straight bar is trimmed equally at both ends to a whole 25 mm, clear of the snap distance',
      abs((hi - lo) - 2725.0) < 1e-6 and abs(lo - 68.5) < 1e-6)
lo, hi = wr._trim_to_step_mm(50.0, 2873.0)
check('a trim already clear of the snap distance is kept', abs((hi - lo) - 2800.0) < 1e-6)
check('an exact 25 mm length is left alone', wr._trim_to_step_mm(0.0, 2775.0) == (0.0, 2775.0))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'lib'))
from nosa_utils import standards
check('laps and anchorages round up to 25 mm',
      standards.round_up_mm(733.6) == 750.0 and standards.round_up_mm(750.0) == 750.0
      and standards.round_down_mm(2762.0) == 2750.0)
print('\nALL 25 MM DETAILING CHECKS PASSED')

import beam_rebar as br
check('beam leg: anchorage not given by the straight length, at least 12 phi, within the beam',
      br.support_leg_mm(800.0, 405.0, 20.0, 500.0) == 395.0
      and br.support_leg_mm(800.0, 700.0, 20.0, 500.0) == 240.0
      and br.support_leg_mm(1200.0, 100.0, 20.0, 500.0) == 480.0)
print('\nALL BEAM ANCHORAGE CHECKS PASSED')

check('wall verticals: whole 25 mm, never ending within the snap distance of the cover',
      wr.whole_step_length_mm(2620.0) == 2600.0 and wr.whole_step_length_mm(2606.0) == 2575.0
      and wr.whole_step_length_mm(2600.0) == 2600.0)
print('\nALL WALL LENGTH CHECKS PASSED')
