# -*- coding: utf-8 -*-
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import geometry
from nosa_utils.revit_helpers import get_id_value
from nosa_utils import unit_conversion as _uc
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

MAX_CHANGE_WARNING_THRESHOLD = 0.3
MIN_BEAM_LENGTH_FT = 0.328
ALIGNED_TOLERANCE_FT = 0.001

DEFAULT_CONFIG = {
    'max_distance_mm': 1000,
    'align_both_ends': True,
    'include_pilecaps': True,
    'include_ground_beams': True,
}


def mm_to_ft(mm):
    return mm * _uc.MM_TO_FT


def ft_to_mm(ft):
    return ft * _uc.FT_TO_MM


# ── Classification ───────────────────────────────────────────────────────────

def _category_value(element):
    try:
        return get_id_value(element.Category.Id)
    except Exception:
        return None


def is_ground_beam(element):
    """Structural foundation with a LocationCurve (behaves like a beam)."""
    try:
        if _category_value(element) != int(DB.BuiltInCategory.OST_StructuralFoundation):
            return False
        return isinstance(element.Location, DB.LocationCurve)
    except Exception:
        return False


def is_pilecap(element):
    return _category_value(element) == int(DB.BuiltInCategory.OST_StructuralFoundation)


def element_label(element):
    if is_ground_beam(element):
        return u"Ground Beam"
    if is_pilecap(element):
        return u"Pilecap"
    return u"Beam"


def classify_selection(elements):
    """Split a selection into beams, ground beams, pilecaps and columns."""
    framing = int(DB.BuiltInCategory.OST_StructuralFraming)
    columns = int(DB.BuiltInCategory.OST_StructuralColumns)
    foundation = int(DB.BuiltInCategory.OST_StructuralFoundation)

    sel = {'beams': [], 'ground_beams': [], 'pilecaps': [], 'columns': []}
    for el in elements:
        if not isinstance(el, DB.FamilyInstance):
            continue
        cat = _category_value(el)
        if cat == framing:
            sel['beams'].append(el)
        elif cat == columns:
            sel['columns'].append(el)
        elif cat == foundation:
            if is_ground_beam(el):
                sel['ground_beams'].append(el)
            else:
                sel['pilecaps'].append(el)
    return sel


# ── Geometry ─────────────────────────────────────────────────────────────────

def get_beam_endpoints(beam):
    location = beam.Location
    if isinstance(location, DB.LocationCurve):
        curve = location.Curve
        return curve.GetEndPoint(0), curve.GetEndPoint(1)
    return None, None


def get_element_center(element):
    return geometry.get_element_center(element)


def find_closest_column(point, columns):
    closest_column = None
    min_distance = float('inf')
    for column in columns:
        centre = get_element_center(column)
        if centre:
            dist = geometry.calculate_distance_2d(point, centre)
            if dist < min_distance:
                min_distance = dist
                closest_column = column
    return closest_column, min_distance


def find_closest_column_for_beam(beam, columns, align_both=False):
    """Closest column for each beam end (align_both) or the single closest end/column pair."""
    endpoints = get_beam_endpoints(beam)
    if not endpoints[0] or not endpoints[1]:
        return []

    results = []
    if align_both:
        for end_index, endpoint in enumerate(endpoints):
            column, distance = find_closest_column(endpoint, columns)
            if column:
                results.append({'end_index': end_index, 'endpoint': endpoint,
                                'column': column, 'distance': distance})
        return results

    best = None
    min_distance = float('inf')
    for column in columns:
        centre = get_element_center(column)
        if not centre:
            continue
        for end_index, endpoint in enumerate(endpoints):
            dist = geometry.calculate_distance_2d(endpoint, centre)
            if dist < min_distance:
                min_distance = dist
                best = {'end_index': end_index, 'endpoint': endpoint,
                        'column': column, 'distance': dist}
    if best:
        results.append(best)
    return results


def _is_aligned(point, centre):
    return abs(point.X - centre.X) < ALIGNED_TOLERANCE_FT and \
        abs(point.Y - centre.Y) < ALIGNED_TOLERANCE_FT


# ── Planning ─────────────────────────────────────────────────────────────────

def plan_alignments(sel, align_both_ends, max_distance_mm):
    """Return (beam_alignments, pilecap_alignments, skipped) without touching the model."""
    max_distance_ft = mm_to_ft(max_distance_mm)
    columns = sel['columns']
    beam_alignments = []
    pilecap_alignments = []
    skipped = []

    for beam in sel['beams'] + sel['ground_beams']:
        for result in find_closest_column_for_beam(beam, columns, align_both_ends):
            if result['distance'] > max_distance_ft:
                skipped.append((beam, u"Too far ({:.0f}mm > {}mm)".format(
                    ft_to_mm(result['distance']), max_distance_mm)))
                continue
            centre = get_element_center(result['column'])
            if centre and _is_aligned(result['endpoint'], centre):
                skipped.append((beam, u"Already aligned"))
                continue
            beam_alignments.append({
                'beam': beam,
                'column': result['column'],
                'end_index': result['end_index'],
                'distance_mm': ft_to_mm(result['distance']),
            })

    for pilecap in sel['pilecaps']:
        centre = get_element_center(pilecap)
        if not centre:
            skipped.append((pilecap, u"Could not get centre"))
            continue
        column, distance = find_closest_column(centre, columns)
        if not column:
            skipped.append((pilecap, u"No column found"))
            continue
        if distance > max_distance_ft:
            skipped.append((pilecap, u"Too far ({:.0f}mm > {}mm)".format(
                ft_to_mm(distance), max_distance_mm)))
            continue
        column_centre = get_element_center(column)
        if column_centre and _is_aligned(centre, column_centre):
            skipped.append((pilecap, u"Already aligned"))
            continue
        pilecap_alignments.append({
            'pilecap': pilecap,
            'column': column,
            'distance_mm': ft_to_mm(distance),
        })

    return beam_alignments, pilecap_alignments, skipped


# ── Model changes ────────────────────────────────────────────────────────────

def move_beam_end_keep_level(doc, beam, end_index, new_point):
    """Straight beams: reshape the curve. Curved beams: translate the whole beam."""
    location = beam.Location
    if not isinstance(location, DB.LocationCurve):
        return False, u"Beam does not have location curve", {}

    curve = location.Curve
    old_end_point = curve.GetEndPoint(end_index)
    new_point_with_level = DB.XYZ(new_point.X, new_point.Y, old_end_point.Z)

    if isinstance(curve, DB.Line):
        other_point = curve.GetEndPoint(1 - end_index)
        original_length = curve.Length
        new_length = geometry.calculate_distance_3d(new_point_with_level, other_point)

        if new_length <= doc.Application.ShortCurveTolerance or new_length < MIN_BEAM_LENGTH_FT:
            return False, u"Beam would be too short", {}

        change_ratio = abs(new_length - original_length) / original_length
        warning = None
        if change_ratio > MAX_CHANGE_WARNING_THRESHOLD:
            warning = u"Large change: {:.1f}%".format(change_ratio * 100)

        if end_index == 0:
            location.Curve = DB.Line.CreateBound(new_point_with_level, other_point)
        else:
            location.Curve = DB.Line.CreateBound(other_point, new_point_with_level)

        return True, warning, {
            'original_length_mm': ft_to_mm(original_length),
            'new_length_mm': ft_to_mm(new_length),
            'change_percent': change_ratio * 100,
        }

    translation = DB.XYZ(new_point_with_level.X - old_end_point.X,
                         new_point_with_level.Y - old_end_point.Y, 0)
    DB.ElementTransformUtils.MoveElement(doc, beam.Id, translation)
    return True, u"Curved beam translated", {
        'move_distance_mm': ft_to_mm(translation.GetLength()),
        'is_curved': True,
    }


def move_pilecap_to_column(doc, pilecap, column):
    pilecap_centre = get_element_center(pilecap)
    column_centre = get_element_center(column)
    if not pilecap_centre or not column_centre:
        return False, u"Could not get element centres", {}

    move_vector = DB.XYZ(column_centre.X - pilecap_centre.X,
                         column_centre.Y - pilecap_centre.Y, 0)
    distance = geometry.calculate_distance_2d(pilecap_centre, column_centre)
    DB.ElementTransformUtils.MoveElement(doc, pilecap.Id, move_vector)
    return True, None, {'distance_mm': ft_to_mm(distance)}


def execute_alignments(doc, beam_alignments, pilecap_alignments):
    """Apply every planned alignment in one transaction; returns a result dict."""
    res = {'beams': 0, 'ground_beams': 0, 'pilecaps': 0, 'failed': 0,
           'warnings': [], 'log': []}

    with nosa_tx.guard(DB.Transaction(doc, u"NOSA — Align Elements to Columns")) as t:
        t.Start()
        for a in beam_alignments:
            beam = a['beam']
            label = element_label(beam)
            centre = get_element_center(a['column'])
            if not centre:
                res['failed'] += 1
                continue
            ok, warning, _info = move_beam_end_keep_level(doc, beam, a['end_index'], centre)
            if ok:
                if is_ground_beam(beam):
                    res['ground_beams'] += 1
                else:
                    res['beams'] += 1
                if warning:
                    res['warnings'].append(u"Beam {}: {}".format(beam.Id, warning))
                res['log'].append(u"✓ {} {} aligned".format(label, beam.Id))
            else:
                res['failed'] += 1
                res['log'].append(u"✗ Beam {} failed: {}".format(beam.Id, warning))

        for a in pilecap_alignments:
            pilecap = a['pilecap']
            ok, warning, info = move_pilecap_to_column(doc, pilecap, a['column'])
            if ok:
                res['pilecaps'] += 1
                res['log'].append(u"✓ Pilecap {} aligned ({:.0f}mm)".format(
                    pilecap.Id, info.get('distance_mm', 0)))
            else:
                res['failed'] += 1
                res['log'].append(u"✗ Pilecap {} failed: {}".format(pilecap.Id, warning))
        t.Commit()

    return res
