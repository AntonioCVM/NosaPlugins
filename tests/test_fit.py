# -*- coding: utf-8 -*-
"""nosa_utils.fit — IStructE SMDSC 5.2/5.3 fitting checks (T8.47)."""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
from nosa_utils import fit  # noqa: E402


def test_table_5_5_deductions():
    assert fit.closed_deduction_mm(600) == 10 and fit.closed_deduction_mm(1500) == 15
    assert fit.closed_deduction_mm(2500) == 20 and fit.closed_deduction_mm(600, bent=False) == 40


def test_smdsc_example_2_five_h32_do_not_fit_in_a_275_beam():
    """SMDSC 5.3 example 2: 275 wide, 40 cover, H12 links -> about 159 mm inside; 5 H32 need 176."""
    space = fit.space_inside_links_mm(275.0, 40.0, 12.0)
    assert abs(space - 159.0) < 1.0, space   # SMDSC: 275 - 80 - 2(12 + 1) - 10 = 159
    fits, _gap = fit.bars_fit(space, 5, 32.0)
    assert not fits
    assert 5 * fit.actual_size_mm(32.0) > 175.0


def test_min_clear_and_mesh_notes():
    assert fit.min_clear_mm(16.0) == 25.0 and fit.min_clear_mm(32.0) == 32.0
    assert fit.mesh_spacing_notes(200.0, 16.0) == []
    assert fit.mesh_spacing_notes(90.0, 16.0)            # under the 100 mm pitch at laps
    assert len(fit.mesh_spacing_notes(40.0, 20.0)) == 2  # clear gap and minimum pitch


def test_layer_notes_and_capacity():
    assert fit.layer_notes(300.0, 40.0, 8.0, 3, 20.0) == []
    notes = fit.layer_notes(300.0, 40.0, 8.0, 5, 25.0)
    assert notes and u'at most 4 per layer' in notes[0], notes
    assert fit.max_bars_in(fit.space_inside_links_mm(300.0, 40.0, 8.0), 25.0) == 4
