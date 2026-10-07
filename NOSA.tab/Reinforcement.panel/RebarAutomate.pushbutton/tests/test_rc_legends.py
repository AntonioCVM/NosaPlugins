# -*- coding: utf-8 -*-
"""rc_legends (T8.31/T8.32): SMDSC notes text, layer notation key and panel B stacking."""
from __future__ import print_function, unicode_literals
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))
import rc_legends as rl


def test_notes_take_the_project_values():
    text = rl.notes_text(u'C40/50', u'50mm', u'40mm')
    assert text.startswith(u'REINFORCEMENT NOTES')
    assert u'Concrete grade C40/50' in text
    assert u'50mm typical, 40mm slabs' in text
    assert u'20H16-63-150 B1' in text and u'BS 8666:2020' in text
    print(u'[PASS] test_notes_take_the_project_values')


def test_notes_without_values_point_to_the_general_notes():
    text = rl.notes_text(u'', u'', u'')
    assert u'Concrete grade to the general notes' in text
    assert u'links included: to the general notes' in text
    print(u'[PASS] test_notes_without_values_point_to_the_general_notes')


def test_notation_key_has_every_smdsc_layer():
    labels = set(d[2] for k, d in rl.notation_sketch() if k == 'text')
    assert set([u'T1', u'T2', u'B1', u'B2', u'N1', u'N2', u'F1', u'F2']) <= labels
    print(u'[PASS] test_notation_key_has_every_smdsc_layer')


def test_legends_stack_down_panel_b_right_aligned():
    x0, y0, x1, y1 = rl.PANEL_B
    centres = rl.stack_in_panel([(60.0, 100.0), (90.0, 60.0)])
    assert centres[0] == (x1 - 30.0, y1 - 50.0)
    assert centres[1] == (x1 - 45.0, y1 - 100.0 - rl.PANEL_GAP_MM - 30.0)
    print(u'[PASS] test_legends_stack_down_panel_b_right_aligned')


if __name__ == '__main__':
    test_notes_take_the_project_values()
    test_notes_without_values_point_to_the_general_notes()
    test_notation_key_has_every_smdsc_layer()
    test_legends_stack_down_panel_b_right_aligned()
