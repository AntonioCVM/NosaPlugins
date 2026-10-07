# -*- coding: utf-8 -*-
"""fit_checks (T8.47): SMDSC 5.2/5.3 fitting notes for meshes, beams and columns."""
from __future__ import print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'lib'))
import fit_checks as fc


def test_meshes_every_direction():
    assert fc.mesh_notes('walls', {'vert_dia': 16, 'vert_spacing': 200, 'horiz_dia': 12, 'horiz_spacing': 200}) == []
    notes = fc.mesh_notes('footings_floors', {'dia_x': 20, 'dia_y': 20, 'spacing': 60, 'include_top_mat': True,
                                              'top_dia_x': 12, 'top_dia_y': 12, 'top_spacing': 150})
    assert any(u'Bottom mat X' in n for n in notes) and not any(u'Top mat' in n for n in notes)
    print(u'[PASS] test_meshes_every_direction')


def test_beam_and_column_layers():
    assert fc.beam_notes(300.0, 40.0, 8.0, 20.0, 3, 3) == []
    assert fc.beam_notes(300.0, 40.0, 8.0, 25.0, 5, 3)          # 5H25 in a 300 beam
    rect = {'shape': 'rect', 'width_mm': 300.0, 'depth_mm': 300.0}
    assert fc.column_notes(rect, 40.0, 8.0, 16.0, 8, (3, 3)) == []
    assert fc.column_notes(rect, 40.0, 8.0, 32.0, 16, (5, 5))
    circle = {'shape': 'circle', 'diameter_mm': 300.0}
    assert fc.column_notes(circle, 40.0, 8.0, 16.0, 6, (0, 0)) == []
    assert fc.column_notes(circle, 40.0, 8.0, 32.0, 14, (0, 0))
    print(u'[PASS] test_beam_and_column_layers')


if __name__ == '__main__':
    test_meshes_every_direction()
    test_beam_and_column_layers()
