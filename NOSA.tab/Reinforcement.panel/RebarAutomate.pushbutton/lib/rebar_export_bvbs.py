# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BVBS (.abs) export, BF2D records (T4.1).

Written to the BVBS Guideline "Data exchange of reinforcement data" 3.1
(Bundesverband Bausoftware, May 2021): header block H (j r i p l n e d g s v),
geometry block G (l / w per leg, outer dimensions, last bend 0), checksum
block C (96 - sum of ASCII codes up to and including "C", mod 32), CRLF.
tests/test_rebar_export_bvbs.py rebuilds the guideline's own worked examples
byte for byte. Bars that are not a planar line/bend chain (lapped circular
links, custom shapes) are written with header and checksum only, as the
guideline prescribes for shapes the interface cannot describe.

Revit-free, so it is testable outside Revit.
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

from nosa_utils.compat import text_type  # noqa: E402

BVBS_FORMAT_VERIFIED = True
BVBS_GUIDELINE = u'BVBS Guideline 3.1 (2021-05)'


# T8.16 (user decision 2026-10-04): the header length is the sum of the outer dimensions, as in the
# ZEICON reference record (tests); the machine derives the cut length from the mandrel
LENGTH_NOTE = (u'Note: bar lengths in the .abs are the sum of the outer dimensions (BVBS); '
               u'the BBS shows the cut length.')

def checksum(record_up_to_c):
    """BVBS checksum of everything from the start of the record up to and including the 'C'."""
    return 96 - sum(ord(ch) for ch in record_up_to_c) % 32


def _text(value):
    """Free text: '@' is the field separator, so it may not appear inside a field."""
    return text_type(value if value is not None else u'').replace(u'@', u'').strip()


def _number(value, decimals=0):
    """mm values as integers; others with at most `decimals` places, no trailing zeros."""
    if decimals == 0:
        return text_type(int(round(value)))
    txt = (u'{:.%df}' % decimals).format(value).rstrip(u'0').rstrip(u'.')
    return txt if txt not in (u'', u'-0') else u'0'


def geometry_block(legs):
    """G block from [(outer_length_mm, signed_bend_deg), ...]; the last bend must be 0."""
    fields = []
    for i, (length_mm, angle_deg) in enumerate(legs):
        angle = 0.0 if i == len(legs) - 1 else angle_deg
        fields.append(u'l{}@w{}@'.format(_number(length_mm), _number(angle, 2)))
    return u'G' + u''.join(fields)


def bvbs_record(position, project_no=u'', schedule_no=u'', revision=u'', steel_grade=u'B500B'):
    """
    One BF2D record (without CRLF) for a schedule position: mark, diameter_mm, count,
    unit_length_mm, and optionally legs / mandrel_mm / unit_weight_kg.
    """
    dia = float(position.get('diameter_mm') or 0)
    legs = position.get('legs') or []
    if legs:
        length_mm = sum(l for l, _a in legs)   # header length = sum of outer legs
    else:
        length_mm = float(position.get('unit_length_mm') or 0.0)
    weight = position.get('unit_weight_kg')
    if weight is None:
        weight = (dia ** 2 / 162.0) * float(position.get('unit_length_mm') or length_mm) / 1000.0
    mandrel = position.get('mandrel_mm') or 4.0 * dia   # guideline default 4·ds

    header = (u'Hj{}@r{}@i{}@p{}@l{}@n{}@e{}@d{}@g{}@s{}@v@{}'.format(
        _text(project_no), _text(schedule_no), _text(revision), _text(position.get('mark', u'?')),
        _number(length_mm), int(position.get('count') or 0) * max(1, int(position.get('members') or 1)),
        _number(weight, 3),
        _number(dia), _text(steel_grade), _number(mandrel),
        u'c{}@'.format(_text(position['group'])) if position.get('group') else u''))
    body = u'BF2D@' + header + (geometry_block(legs) if legs else u'') + u'C'
    return u'{}{}@'.format(body, checksum(body))


def export_bvbs_file(schedule_data, output_path, project_no=u'', schedule_no=u'',
                     revision=u'', steel_grade=u'B500B'):
    """Write one .abs file; returns (records written, records without geometry)."""
    lines = []
    without_geometry = 0
    for pos in schedule_data:
        if not pos.get('legs'):
            without_geometry += 1
        # marks restart in every partition, so each partition is its own drawing (field r)
        drawing = u'{}-{}'.format(schedule_no, pos['member']) if pos.get('member') else schedule_no
        lines.append(bvbs_record(pos, project_no, drawing, revision, steel_grade))
    with io.open(output_path, 'w', encoding='ascii', errors='replace', newline='') as f:
        for line in lines:
            f.write(line + u'\r\n')
    return len(lines), without_geometry
