# -*- coding: utf-8 -*-
"""rebar_export_bvbs / rebar_bending against the BVBS Guideline 3.1 worked examples (T4.1)."""
from __future__ import absolute_import, print_function, unicode_literals
import io
import os
import sys
import tempfile

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from rebar_export_bvbs import BVBS_FORMAT_VERIFIED, bvbs_record, checksum, export_bvbs_file  # noqa: E402
from rebar_bending import arc_segment, bending_legs, line_segment  # noqa: E402

# Header shared by the guideline's BF2D examples (pages 20-21).
_JOB = dict(project_no=u'TestPDF', schedule_no=u'417', revision=u'a', steel_grade=u'B500A')


def _position(legs, weight, count=10):
    return {'mark': u'1', 'diameter_mm': 12, 'count': count, 'legs': legs,
            'mandrel_mm': 48, 'unit_weight_kg': weight}


def test_guideline_checksum_example():
    assert checksum(u'abcde@C') == 78


def test_guideline_example_1_l_bar():
    rec = bvbs_record(_position([(400, 90), (600, 0)], 0.888), **_JOB)
    assert rec == (u'BF2D@HjTestPDF@r417@ia@p1@l1000@n10@e0.888@d12@gB500A@s48@v@'
                   u'Gl400@w90@l600@w0@C72@'), rec


def test_guideline_example_3_signed_angles():
    legs = [(100, 90), (300, 45), (424, -45), (300, -90), (100, 0)]
    rec = bvbs_record(_position(legs, 1.087), **_JOB)
    assert rec == (u'BF2D@HjTestPDF@r417@ia@p1@l1224@n10@e1.087@d12@gB500A@s48@v@'
                   u'Gl100@w90@l300@w45@l424@w-45@l300@w-90@l100@w0@C82@'), rec


def test_guideline_zeicon_decimal_angles():
    # Page 5, position 3 (the PDF wraps the project name; its checksum is for "ZEICON Bewehrungslis").
    pos = {'mark': u'3', 'diameter_mm': 16, 'count': 51, 'mandrel_mm': 64, 'unit_weight_kg': 7.268,
           'legs': [(1135, 79.7), (350, 90), (1630, 90), (350, 79.7), (1135, 0)]}
    rec = bvbs_record(pos, project_no=u'ZEICON Bewehrungslis', schedule_no=u'ZEICON', revision=u'1',
                      steel_grade=u'BSt500S')
    body = rec[:rec.index(u'@C') + 2]
    assert body == (u'BF2D@HjZEICON Bewehrungslis@rZEICON@i1@p3@l4600@n51@e7.268@d16@gBSt500S@s64@v@'
                    u'Gl1135@w79.7@l350@w90@l1630@w90@l350@w79.7@l1135@w0@C')


def test_guideline_example_9_staggered_bars():
    rows = [(u'10.1', 300, 700.0, 0.522), (u'10.2', 600, 1000.0, 0.888), (u'10.3', 900, 1300.0, 1.154)]
    recs = [bvbs_record({'mark': mark, 'group': u'10', 'diameter_mm': 12, 'mandrel_mm': 48, 'count': 1,
                         'legs': [(400, 90), (leg, 0)], 'unit_length_mm': length, 'unit_weight_kg': weight},
                        **_JOB) for mark, leg, length, weight in rows]
    assert recs == [
        u'BF2D@HjTestPDF@r417@ia@p10.1@l700@n1@e0.522@d12@gB500A@s48@v@c10@Gl400@w90@l300@w0@C65@',
        u'BF2D@HjTestPDF@r417@ia@p10.2@l1000@n1@e0.888@d12@gB500A@s48@v@c10@Gl400@w90@l600@w0@C68@',
        u'BF2D@HjTestPDF@r417@ia@p10.3@l1300@n1@e1.154@d12@gB500A@s48@v@c10@Gl400@w90@l900@w0@C74@',
    ], recs


def test_no_geometry_record_has_header_and_checksum_only():
    rec = bvbs_record({'mark': u'C7', 'diameter_mm': 10, 'count': 12, 'unit_length_mm': 1540.0}, **_JOB)
    assert u'@G' not in rec and rec.startswith(u'BF2D@Hj') and rec.endswith(u'@')
    assert u'@l1540@n12@' in rec and u'@s40@' in rec   # default mandrel 4·ds
    assert int(rec[rec.index(u'@C') + 2:-1]) == checksum(rec[:rec.index(u'@C') + 2])


def test_at_sign_removed_from_free_text():
    rec = bvbs_record(_position([(400, 0)], 0.3), project_no=u'P@1', schedule_no=u'1')
    assert u'Hjp1' not in rec and u'HjP1@' in rec


def test_bending_legs_u_bar_outer_dimensions():
    # Revit centreline of a H10 U-bar (Rebar test model): 370 / r25 90° / 756 / r25 90° / 370.
    segs = [line_segment(370, (1, 0, 0)), arc_segment(25, 90), line_segment(756, (0, 0, 1)),
            arc_segment(25, 90), line_segment(370, (-1, 0, 0))]
    result = bending_legs(segs, 10.0)
    assert result['mandrel_mm'] == 40.0
    lengths = [round(l, 6) for l, _a in result['legs']]
    assert lengths == [400.0, 816.0, 400.0], lengths
    angles = [a for _l, a in result['legs']]
    assert abs(angles[0] - angles[1]) < 1e-9 and abs(abs(angles[0]) - 90) < 1e-9 and angles[2] == 0.0


def test_bending_legs_zigzag_signs_differ():
    segs = [line_segment(500, (1, 0, 0)), arc_segment(24, 90), line_segment(300, (0, 1, 0)),
            arc_segment(24, 90), line_segment(500, (1, 0, 0))]
    angles = [a for _l, a in bending_legs(segs, 12.0)['legs']]
    assert angles[0] == -angles[1] and angles[2] == 0.0


def test_bending_legs_straight_and_circle():
    assert bending_legs([line_segment(1920, (1, 0, 0))], 16.0) == {'legs': [(1920.0, 0.0)],
                                                                   'mandrel_mm': None}
    circle = [arc_segment(180, 180), arc_segment(180, 127.3), arc_segment(180, 180)]
    assert bending_legs(circle, 10.0) is None


def test_export_file_crlf_and_count():
    data = [_position([(400, 90), (600, 0)], 0.888),
            {'mark': u'C7', 'diameter_mm': 10, 'count': 2, 'unit_length_mm': 1540.0}]
    fd, path = tempfile.mkstemp(suffix='.abs')
    os.close(fd)
    try:
        written, without_geometry = export_bvbs_file(data, path, **_JOB)
        raw = io.open(path, 'rb').read()
    finally:
        os.remove(path)
    assert (written, without_geometry) == (2, 1)
    assert raw.count(b'\r\n') == 2 and b'\n\n' not in raw and raw.startswith(b'BF2D@')


def test_flag_records_guideline_check():
    assert BVBS_FORMAT_VERIFIED is True


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(t.__name__, 'OK')
    print('\nALL BVBS CHECKS PASSED ({})'.format(len(tests)))
