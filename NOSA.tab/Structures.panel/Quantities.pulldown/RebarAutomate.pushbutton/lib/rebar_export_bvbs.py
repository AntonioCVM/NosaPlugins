# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BVBS (.abs) export. Roadmap F8.

*** FORMAT CONFIDENCE WARNING — READ BEFORE SENDING TO A REAL MACHINE ***
BVBS (Bausoftware-Verband Bewehrungsschnittstelle) is a real, published
German interface standard that CNC bending machines (Schnell, EVG, MEP,
...) read directly. This module produces a BEST-EFFORT approximation of
its BF2D record structure — record type, order/position identifiers,
steel grade, diameter, quantity, shape code, ordered segment lengths,
total length, then a checksum — because at the time this was written NO
official BVBS specification document and NO real .abs fixture accepted
by an actual machine or validator was available to confirm exact field
widths, separators, units (e.g. whether diameter is encoded in mm or in
1/10 mm) or the checksum algorithm (published BVBS-derived tools use more
than one checksum scheme; this module picks ONE and says so).

BVBS_FORMAT_VERIFIED (below) is False and MUST stay False until someone
has actually checked a file this module produced against an official
BVBS validator or a real bending machine. Until then:
  - Do NOT send output from this module to a real fabricator.
  - DO trust the DATA EXTRACTION (mark, diameter, shape, segment lengths,
    quantities) — that part reuses rebar_schedule.generate_schedule_data,
    already exercised by F5's own tests, and is entirely NOSA's own,
    Revit-side responsibility, independent of the external byte format.
  - The exact byte-level layout is isolated in bar_to_bvbs_line() and
    _compute_checksum() specifically so it can be corrected later without
    touching the Revit-side data extraction at all.

Kept deliberately Revit-free (no `Autodesk.Revit`/`pyrevit` imports) —
same "pure formatting" boundary as rebar_schedule.export_csv/export_xlsx —
so this is testable without a live Revit session.
"""
from __future__ import absolute_import, print_function, unicode_literals
import io
import os
import sys

# Same self-contained sys.path convention as rebar_schedule.py/rebar_batch.py
# — this module can be imported standalone (a pure pytest file, no live
# Revit session) without the extension-wide lib/ dir already on sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_EXT_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

from nosa_utils.compat import text_type  # noqa: E402

BVBS_FORMAT_VERIFIED = False

# Segment-letter keys that are shape DIMENSIONS (become BVBS segment
# fields, in alphabetical order — matching NOSA_Rebar_Shape_Params'
# own "A=..;B=..;C=.." convention, see rebar_marking._parse_shape_params).
# 'R' (bend/mandrel radius) is excluded — BVBS carries bend radius via the
# bar type's own mandrel diameter, not as a straight segment length.
_RADIUS_KEY = u'R'


def parse_shape_params(shape_params_str):
    """
    Parse NOSA_Rebar_Shape_Params ("A=2000;B=300;C=150;R=50") into an
    ordered list of (key, value_mm) tuples, sorted alphabetically by key —
    the exact same parsing rule rebar_marking._parse_shape_params applies
    for dedup, kept independent here (this module has no Revit/document
    access) so a caller only needs the plain string value already read
    via shared_params elsewhere.
    """
    if not shape_params_str or not isinstance(shape_params_str, text_type):
        return []
    pairs = []
    for chunk in shape_params_str.split(u';'):
        chunk = chunk.strip()
        if u'=' not in chunk:
            continue
        key, val = chunk.split(u'=', 1)
        key = key.strip()
        try:
            pairs.append((key, float(val.strip())))
        except ValueError:
            continue
    return sorted(pairs, key=lambda kv: kv[0])


def segments_from_position(position):
    """
    Ordered list of (letter, length_mm) segments for one schedule
    position dict (see rebar_schedule.generate_schedule_data), excluding
    the bend-radius key.
    """
    params = parse_shape_params(position.get('shape_params', u''))
    return [(k, v) for k, v in params if k.upper() != _RADIUS_KEY]


def _compute_checksum(payload):
    """
    *** UNVERIFIED — see module docstring. *** Best-effort checksum: sum
    of the Unicode code point of every character in `payload`, modulo
    100, as a zero-padded 2-digit string. Isolated in its own function so
    a confirmed real algorithm can replace this single function later
    without touching bar_to_bvbs_line's field layout.
    """
    total = sum(ord(c) for c in payload)
    return u'{:02d}'.format(total % 100)


def bar_to_bvbs_line(position, order_no=u'1', steel_grade=u'B500B'):
    """
    Best-effort single BF2D record line for one schedule position dict
    (rebar_schedule.generate_schedule_data's return shape: mark,
    diameter_mm, count, shape_code, shape_params, unit_length_mm, ...).

    *** UNVERIFIED FIELD LAYOUT — see module docstring. *** Field order
    below (record type, version, order, position, steel grade, diameter,
    quantity, shape code, total length, then one signed field per shape
    segment, then a checksum) follows BVBS's publicly-documented
    CONCEPTUAL structure; exact column widths/units have not been
    checked against the official spec or a real fixture.

    Returns:
        unicode: one BF2D record line, WITHOUT a trailing newline.
    """
    mark = text_type(position.get('mark', u'?'))
    dia_mm = int(position.get('diameter_mm', 0) or 0)
    count = int(position.get('count', 0) or 0)
    shape_code = text_type(position.get('shape_code', u'99'))
    total_len_mm = int(round(position.get('unit_length_mm', 0.0) or 0.0))
    segments = segments_from_position(position)

    fields = [
        u'BF2D',
        u'01',                                    # format version — best effort
        u'{:>8.8}'.format(text_type(order_no)),
        u'{:>8.8}'.format(mark),
        u'{:<8.8}'.format(text_type(steel_grade)),
        u'{:04d}'.format(dia_mm),
        u'{:04d}'.format(count),
        u'{:>3.3}'.format(shape_code),
        u'{:06d}'.format(total_len_mm),
    ]
    for _letter, length_mm in segments:
        sign = u'+' if length_mm >= 0 else u'-'
        fields.append(u'{}{:05d}'.format(sign, int(round(abs(length_mm)))))

    payload = u''.join(fields)
    return payload + _compute_checksum(payload)


def export_bvbs_file(schedule_data, output_path, order_no=u'1', steel_grade=u'B500B'):
    """
    Write one .abs file with one best-effort BF2D line per schedule
    position (see bar_to_bvbs_line — and the module docstring's format
    warning before relying on the output for real fabrication).

    Args:
        schedule_data (list[dict]): rebar_schedule.generate_schedule_data's
                        return value.
        output_path   (unicode/str): destination .abs file path.
        order_no      (unicode): order/job number stamped on every line.
        steel_grade   (unicode): steel grade stamped on every line — NOSA
                        does not yet track a per-bar steel grade
                        (Roadmap item, see standards.py's own
                        steel.default_grade), so this is currently one
                        fixed value for the whole export, not read per
                        position.

    Returns:
        int: number of records written.
    """
    lines = [bar_to_bvbs_line(pos, order_no=order_no, steel_grade=steel_grade)
             for pos in schedule_data]
    with io.open(output_path, 'w', encoding='ascii', errors='replace', newline='\r\n') as f:
        for line in lines:
            f.write(line)
            f.write(u'\n')
    return len(lines)
