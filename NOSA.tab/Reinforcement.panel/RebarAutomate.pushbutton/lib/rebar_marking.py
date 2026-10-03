# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — bar marking (BS 8666:2020).

Identical bars (diameter, shape code, outer dimensions, hooks, cut length) share one
plain sequential mark per partition — 01, 02 ... — reused across batches. A varying
set keeps one mark; its lengths are told apart in the schedule and the BVBS file by
letter suffixes (05A, 05B ... without I, O, Q). Host ids never enter the mark.
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys, os
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import compat, shared_params, standards
from nosa_utils.compat import text_type

_FT_TO_MM = 304.8


# BUG FIX (2026-09-01) — every call site in this file called
# shared_params.read/write as (doc, rebar_id, name[, value]), but the
# real signatures are read(elem, guid_or_name, default=None) and
# write(elem, guid_or_name, value) — an ELEMENT first, no `doc` at all.
# `read(doc, id, name)` silently bound `doc` to `elem` (wrong) and the
# field name to `default` (wrong) without raising — read calls never
# actually worked, just returned wrong values with no visible error.
# `write(doc, id, name, value)` — 4 args against a 3-arg signature —
# raised outright: "Marking failed: write() takes exactly 3 arguments
# (4 given)" on every single batch run, live-reported, aborting F3
# marking entirely (NOSA_Rebar_Mark/Number/Layer/Total_Length never
# actually got stamped). These two thin wrappers keep every call site
# in this file at its existing (doc, rebar_id, name[, value]) shape —
# only replacing shared_params.read(/write( with _read(/_write( below —
# while routing to the real element-first API underneath.
def _read(doc, rebar_id, name, default=None):
    elem = doc.GetElement(rebar_id)
    if elem is None:
        return default
    return shared_params.read(elem, name, default)


def _write(doc, rebar_id, name, value):
    elem = doc.GetElement(rebar_id)
    if elem is None:
        return False
    return shared_params.write(elem, name, value)


def _round_to_tolerance(value_mm, tolerance_mm):
    """Redondea value_mm al múltiplo más cercano de tolerance_mm."""
    if tolerance_mm <= 0:
        return value_mm
    return round(value_mm / tolerance_mm) * tolerance_mm


def _parse_shape_params(shape_params_str, tolerance_mm):
    """
    Parsea NOSA_Rebar_Shape_Params (formato: "A=2000;B=300;C=150;R=50")
    y devuelve tuple de valores redondeados a tolerance_mm.
    """
    if not shape_params_str or not isinstance(shape_params_str, text_type):
        return ()
    
    params = {}
    for pair in shape_params_str.split(';'):
        pair = pair.strip()
        if '=' in pair:
            key, val = pair.split('=', 1)
            try:
                params[key.strip()] = float(val.strip())
            except ValueError:
                continue
    
    # Ordenar por clave alfabética y redondear
    sorted_keys = sorted(params.keys())
    return tuple(_round_to_tolerance(params[k], tolerance_mm) for k in sorted_keys)


_SUFFIX_LETTERS = u'ABCDEFGHJKLMNPRSTUVWXYZ'   # I, O and Q left out: read as 1 and 0 on site


def variant_suffix(index):
    """Letter suffix of the index-th bar length of a varying set: A..Z, then AA, AB ..."""
    n = index + 1
    out = u''
    while n > 0:
        n, r = divmod(n - 1, len(_SUFFIX_LETTERS))
        out = _SUFFIX_LETTERS[r] + out
    return out


def mark_number(mark):
    """Sequential number of a bar mark ('05', '05B' -> 5); 0 when there is none."""
    digits = u''
    for ch in (mark or u''):
        if not ch.isdigit():
            break
        digits += ch
    return int(digits) if digits else 0


def format_mark(number):
    """BS 8666 bar mark: a plain sequential number, 01, 02 ... 100."""
    return u'{:02d}'.format(int(number))


def _bar_diameter_mm(doc, rebar):
    try:
        bar_type = doc.GetElement(rebar.GetTypeId())
        try:
            return bar_type.BarNominalDiameter * _FT_TO_MM
        except AttributeError:
            return bar_type.BarModelDiameter * _FT_TO_MM
    except Exception:
        return 0.0


def _partition(rebar):
    from Autodesk.Revit import DB  # Lazy import
    try:
        return rebar.get_Parameter(DB.BuiltInParameter.NUMBER_PARTITION_PARAM).AsString() or u''
    except Exception:
        return u''


def _is_varying(doc, rebar):
    """True if the bars of this Rebar element differ in shape or length (a varying set)."""
    import rebar_bending
    bars = rebar_bending.bar_variants(rebar, _bar_diameter_mm(doc, rebar))
    return len(set(rebar_bending.variant_key(geometry, length) for geometry, length in bars)) > 1


def _dedup_key(doc, rebar, tolerance_mm, is_varying):
    """
    Identical bars share a mark (BS 8666): same diameter, shape code, outer dimensions,
    hooks and cut length. A varying set is unique: it keeps one mark of its own.
    """
    rid = rebar.Id
    if is_varying:
        from nosa_utils.revit_helpers import get_id_value
        return ('varying', get_id_value(rid))
    import rebar_bending
    unit_length_mm = rebar_bending.unit_cut_length_mm(rebar)
    return (int(round(_bar_diameter_mm(doc, rebar))),
            _read(doc, rid, "NOSA_Rebar_Shape_Code") or "99",
            _parse_shape_params(_read(doc, rid, "NOSA_Rebar_Shape_Params") or "", tolerance_mm),
            _read(doc, rid, "NOSA_Rebar_Start_Hook_Type") or "",
            _read(doc, rid, "NOSA_Rebar_End_Hook_Type") or "",
            _round_to_tolerance(unit_length_mm, tolerance_mm))


def _existing_marks(doc, exclude_ids, partition, tolerance_mm):
    """Marks already given in this partition: ({dedup key: number}, highest number)."""
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    numbers = {}
    highest = 0
    collector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Rebar).WhereElementIsNotElementType()
    for rebar in collector:
        if get_id_value(rebar.Id) in exclude_ids or _partition(rebar) != partition:
            continue
        if not _read(doc, rebar.Id, "NOSA_Rebar_Batch_Id"):
            continue
        number = mark_number(_read(doc, rebar.Id, "NOSA_Rebar_Mark"))
        if number <= 0:
            continue
        highest = max(highest, number)
        varying = _read(doc, rebar.Id, "NOSA_Rebar_Is_Variable") in (1, u'1')
        numbers.setdefault(_dedup_key(doc, rebar, tolerance_mm, varying), number)
    return numbers, highest


def deduplicate_and_mark(doc, rebars, ctx):
    """
    BS 8666 marking (T4.2, user decision 2026-09-30): identical bars share one sequential
    number per partition (01, 02 ...), reused across batches; host ids never enter the mark.
    Stamps NOSA_Rebar_Mark / _Number / _Is_Variable, the native Schedule Mark (what the tag
    shows; the native Mark would raise duplicate-Mark warnings) and the native Partition.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    std = ctx.get("standard")
    marking_cfg = std.get("marking", {}) if std else {}
    tolerance_mm = marking_cfg.get("dedup_tolerance_mm", 5.0)
    partition = (ctx.get("mark_prefix") or u'').strip()

    elements = [doc.GetElement(rid) for rid in rebars]
    elements = [e for e in elements if e is not None]
    known, highest = _existing_marks(
        doc, set(get_id_value(e.Id) for e in elements), partition, tolerance_mm)

    clusters = {}
    varying_ids = set()
    for rebar in elements:
        varying = _is_varying(doc, rebar)
        if varying:
            varying_ids.add(get_id_value(rebar.Id))
        clusters.setdefault(_dedup_key(doc, rebar, tolerance_mm, varying), []).append(rebar)

    def cluster_order(item):
        key, members = item
        first = members[0]
        params = _read(doc, first.Id, "NOSA_Rebar_Shape_Params") or ""
        a_mm = 0.0
        if 'A=' in params:
            try:
                a_mm = float(params.split('A=')[1].split(';')[0])
            except (IndexError, ValueError):
                log_swallowed(_LOG, u'cluster_order')
        return (-_bar_diameter_mm(doc, first), _read(doc, first.Id, "NOSA_Rebar_Shape_Code") or "99",
                -a_mm, get_id_value(first.Id))

    next_number = highest + 1
    total_bars = 0
    largest_cluster = 0
    reused = 0
    for key, members in sorted(clusters.items(), key=cluster_order):
        number = known.get(key)
        if number is None:
            number = next_number
            next_number += 1
            known[key] = number
        else:
            reused += 1
        mark = format_mark(number)
        total_bars += len(members)
        largest_cluster = max(largest_cluster, len(members))
        for pos_idx, rebar in enumerate(members, start=1):
            _write(doc, rebar.Id, "NOSA_Rebar_Mark", mark)
            _write(doc, rebar.Id, "NOSA_Rebar_Number", number)
            _write(doc, rebar.Id, "NOSA_Rebar_Position_In_Host", pos_idx)
            _write(doc, rebar.Id, "NOSA_Rebar_Is_Variable",
                   1 if get_id_value(rebar.Id) in varying_ids else 0)
            for bip, value in ((DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK, mark),
                               (DB.BuiltInParameter.NUMBER_PARTITION_PARAM, partition)):
                try:
                    param = rebar.get_Parameter(bip)
                    if param is not None and not param.IsReadOnly:
                        param.Set(value)
                except Exception:
                    log_swallowed(_LOG, u'deduplicate_and_mark')

    return {
        "total_positions": len(clusters),
        "total_bars": total_bars,
        "largest_cluster": largest_cluster,
        "reused_marks": reused,
        "varying_sets": len(varying_ids),
    }


def compute_total_length_mm(rebar):
    """
    Calcula longitud total de 'rebar' en mm (incluyendo tramos rectos + ganchos), redondeada.
    Usa Rebar.TotalLength (en pies internos) * FT_TO_MM.
    """
    if not rebar:
        return 0.0
    
    try:
        total_length_ft = rebar.TotalLength
        return round(total_length_ft * _FT_TO_MM, 1)
    except Exception:
        return 0.0


def assign_layers_and_lengths(doc, rebars, ctx):
    """
    Post-proceso: para cada barra en 'rebars' (ElementIds):
    - Si NOSA_Rebar_Layer está vacío, asigna "uncategorized"
    - Calcula y sella NOSA_Rebar_Total_Length
    """
    for rebar_id in rebars:
        layer = _read(doc, rebar_id, "NOSA_Rebar_Layer")
        if not layer or not isinstance(layer, text_type) or layer.strip() == "":
            _write(doc, rebar_id, "NOSA_Rebar_Layer", "uncategorized")
        
        rebar = doc.GetElement(rebar_id)
        if rebar:
            total_length = compute_total_length_mm(rebar)
            _write(doc, rebar_id, "NOSA_Rebar_Total_Length", total_length)


def renumber_partition(doc, ctx):
    """Renumber every non-finalized NOSA bar of the partition; finalized bars keep their marks."""
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory  # Lazy import
    partition = (ctx.get("mark_prefix") or u'').strip()
    rebars = []
    collector = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Rebar).WhereElementIsNotElementType()
    for rebar in collector:
        if not _read(doc, rebar.Id, "NOSA_Rebar_Batch_Id"):
            continue
        if _read(doc, rebar.Id, "NOSA_Rebar_Finalized") in (1, u'1'):
            continue
        current = _partition(rebar)
        if current and current != partition:
            continue
        rebars.append(rebar.Id)
    if not rebars:
        return {"total_positions": 0, "total_bars": 0, "largest_cluster": 0}
    assign_layers_and_lengths(doc, rebars, ctx)
    return deduplicate_and_mark(doc, rebars, ctx)
