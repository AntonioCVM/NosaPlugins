# -*- coding: utf-8 -*-
"""T8.13: 0900 General notes values and the anchorage & lap table."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lib'))

from nosa_utils import general_notes as gn  # noqa: E402

# the template's table (C25/30) as drawn on 0900, per diameter in note order
TEMPLATE = {
    8: [230, 330, 320, 460, 320, 460, 340, 490],
    10: [320, 450, 410, 580, 440, 630, 470, 680],
    12: [410, 580, 490, 700, 570, 820, 610, 876],
    16: [600, 850, 650, 930, 830, 1190, 890, 1270],
    20: [780, 1120, 810, 1160, 1090, 1560, 1170, 1670],
    25: [1010, 1450, 1010, 1450, 1420, 2020, 1520, 2170],
    32: [1300, 1850, 1300, 1850, 1810, 2590, 1940, 2770],
    40: [1760, 2510, 1760, 2510, 2460, 3520, 2640, 3770],
}


def test_anchorage_table_reproduces_the_template_within_its_rounding():
    table = gn.anchorage_table(u'C25/30')
    for dia, expected in TEMPLATE.items():
        got = gn.anchorage_column(table, dia)
        for g, e in zip(got, expected):
            assert abs(g - e) <= 10, (dia, got, expected)


def test_compression_column_matches_the_template():
    assert gn.compression_multiples(u'C25/30') == [40, 58, 40, 58, 57, 81, 61, 87]


def test_stronger_concrete_shortens_anchorage():
    assert gn.anchorage_column(gn.anchorage_table(u'C40/50'), 16)[0] < TEMPLATE[16][0]


NOTE = (u'Concrete strength\r1.\tConcrete strength of all structural elements to be:\r'
        u'\t\t\tConcrete grade  C40/50\rNominal cover\r\t\t\t\t\tTypical\t\t50mm\r\t\t\t\t\tSlabs\t\t\t40mm\r')


def test_slots_read_and_edit_values():
    found = gn.read_text_values([NOTE])
    assert found[u'Concrete_Grade'] == u'C40/50'
    assert found[u'Cover_Typical'] == u'50mm' and found[u'Cover_Slabs'] == u'40mm'
    edits = gn.edits(NOTE, {u'Concrete_Grade': u'C32/40', u'Cover_Slabs': u'40mm'})
    assert [(e[2], e[3]) for e in edits] == [(u'C32/40', u'Concrete_Grade')]
    start, end, value, _key = edits[0]
    assert (NOTE[:start] + value + NOTE[end:]).count(u'C32/40') == 1


def test_line_slots_in_the_wind_table_note():
    note = u'Sea\r27 m/s\r0.75KN\r0.75KN\r-05º to +40º\r 00º to +30º\r'
    found = gn.read_text_values([note])
    assert found[u'Wind_Terrain'] == u'Sea' and found[u'Wind_Speed'] == u'27 m/s'
    assert found[u'Thermal_External'] == u'-05º to +40º'


def test_table_note_refresh():
    note = u'8\r230\r330\r320\r460\r\r320\r\r460\r\r\r340\r\r\r490\r'
    for start, end, value in gn.table_note_edits(note, u'C25/30'):   # the template rounds a few cells by hand
        assert abs(int(value) - int(note[start:end])) <= 10
    assert gn.table_note_edits(note, u'C40/50')
    assert gn.table_note_edits(u'Bond condition\r', u'C40/50') == []


def test_every_field_has_a_parameter_and_default():
    keys = [f[0] for f in gn.FIELDS]
    assert len(keys) == len(set(keys))
    assert all(gn.param_name(k).startswith(u'NOSA_GN_') for k in keys)
