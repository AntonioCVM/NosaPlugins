# -*- coding: utf-8 -*-
"""
Tests puros para rebar_export_bvbs.py (F8).

IMPORTANTE — ver el docstring de rebar_export_bvbs.py: el formato BVBS
byte-a-byte NO está verificado contra un validador oficial ni una
máquina real. Estos tests comprueban invariantes ESTRUCTURALES de las
que sí tenemos certeza (parseo de shape_params, presencia de los campos,
checksum determinista, escritura de fichero) — NO afirman conformidad
con el estándar BVBS real.
"""
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys
import tempfile

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from rebar_export_bvbs import (
    BVBS_FORMAT_VERIFIED, parse_shape_params, segments_from_position,
    bar_to_bvbs_line, export_bvbs_file,
)


def test_format_verified_flag_is_explicitly_false():
    """Guard against silently flipping this to True without ever having
    checked a real validator/machine — see the module's own docstring."""
    assert BVBS_FORMAT_VERIFIED is False


def test_parse_shape_params_basic():
    result = parse_shape_params(u'A=2000;B=300;C=150;R=50')
    assert result == [(u'A', 2000.0), (u'B', 300.0), (u'C', 150.0), (u'R', 50.0)]


def test_parse_shape_params_empty_or_none():
    assert parse_shape_params(u'') == []
    assert parse_shape_params(None) == []


def test_parse_shape_params_ignores_malformed_pairs():
    result = parse_shape_params(u'A=2000;garbage;B=oops;C=150')
    assert result == [(u'A', 2000.0), (u'C', 150.0)]


def test_segments_from_position_excludes_radius():
    position = {'shape_params': u'A=2000;B=300;R=50'}
    segments = segments_from_position(position)
    assert segments == [(u'A', 2000.0), (u'B', 300.0)]


def test_bar_to_bvbs_line_starts_with_record_type():
    position = {
        'mark': u'V1-01', 'diameter_mm': 16, 'count': 4,
        'shape_code': u'11', 'shape_params': u'A=2000;B=300',
        'unit_length_mm': 2300.0,
    }
    line = bar_to_bvbs_line(position)
    assert line.startswith(u'BF2D')


def test_bar_to_bvbs_line_contains_diameter_and_count():
    position = {
        'mark': u'V1-01', 'diameter_mm': 16, 'count': 4,
        'shape_code': u'11', 'shape_params': u'A=2000;B=300',
        'unit_length_mm': 2300.0,
    }
    line = bar_to_bvbs_line(position)
    assert u'0016' in line  # diameter field
    assert u'0004' in line  # count field


def test_bar_to_bvbs_line_is_deterministic():
    position = {
        'mark': u'V1-01', 'diameter_mm': 16, 'count': 4,
        'shape_code': u'11', 'shape_params': u'A=2000;B=300',
        'unit_length_mm': 2300.0,
    }
    assert bar_to_bvbs_line(position) == bar_to_bvbs_line(position)


def test_bar_to_bvbs_line_handles_missing_fields_gracefully():
    line = bar_to_bvbs_line({})
    assert line.startswith(u'BF2D')


def test_export_bvbs_file_writes_one_line_per_position():
    schedule_data = [
        {'mark': u'V1-01', 'diameter_mm': 16, 'count': 4,
         'shape_code': u'11', 'shape_params': u'A=2000;B=300',
         'unit_length_mm': 2300.0},
        {'mark': u'V1-02', 'diameter_mm': 20, 'count': 6,
         'shape_code': u'00', 'shape_params': u'A=4000',
         'unit_length_mm': 4000.0},
    ]
    tmp_path = os.path.join(tempfile.gettempdir(), u'nosa_test_bvbs.abs')
    try:
        count = export_bvbs_file(schedule_data, tmp_path)
        assert count == 2
        with open(tmp_path, 'rb') as f:
            content = f.read().decode('ascii')
        lines = [l for l in content.split(u'\n') if l.strip()]
        assert len(lines) == 2
        assert all(l.startswith(u'BF2D') for l in lines)
    finally:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)


def test_export_bvbs_file_empty_schedule_writes_zero_records():
    tmp_path = os.path.join(tempfile.gettempdir(), u'nosa_test_bvbs_empty.abs')
    try:
        count = export_bvbs_file([], tmp_path)
        assert count == 0
        assert os.path.isfile(tmp_path)
    finally:
        if os.path.isfile(tmp_path):
            os.remove(tmp_path)


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    failures = 0
    for t in tests:
        try:
            t()
            print(u'{}: OK'.format(t.__name__))
        except Exception as e:
            failures += 1
            print(u'{}: FAILED -- {}'.format(t.__name__, e))
    print(u'\n{}/{} tests passed'.format(len(tests) - failures, len(tests)))
    sys.exit(1 if failures else 0)
