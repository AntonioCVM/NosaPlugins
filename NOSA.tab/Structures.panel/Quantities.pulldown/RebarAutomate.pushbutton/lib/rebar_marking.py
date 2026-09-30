# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Motor de numeración y marcado.
Blueprint Parte 8.

Deduplicación: dos barras comparten posición (y marca) si:
- mismo RebarBarType (diámetro)
- misma forma normalizada (Shape_Code + parámetros A,B,C… redondeados)
- mismos ganchos
- mismo NOSA_Rebar_Layer y mismo host (según number_scope)

Barras con Is_Variable=1 nunca deduplicam.
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys, os

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
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


def _get_dedup_key(doc, rebar_id, std, tolerance_mm):
    """
    Devuelve tuple que identifica unicidad de la barra:
    (bar_type_id, shape_code, shape_params_tuple, start_hook_id, end_hook_id, layer, host_id_or_scope)
    
    Si Is_Variable=1, devuelve clave única (el propio rebar_id).
    """
    from Autodesk.Revit import DB  # Lazy import
    
    # Leer shared params
    is_variable = _read(doc, rebar_id, "NOSA_Rebar_Is_Variable")
    if is_variable == 1 or is_variable == "1":
        # Barras variables no deduplicam
        return (rebar_id,)
    
    rebar = doc.GetElement(rebar_id)
    if not rebar:
        return (rebar_id,)
    
    bar_type_id = rebar.GetTypeId()
    shape_code = _read(doc, rebar_id, "NOSA_Rebar_Shape_Code") or "99"
    shape_params_str = _read(doc, rebar_id, "NOSA_Rebar_Shape_Params") or ""
    start_hook = _read(doc, rebar_id, "NOSA_Rebar_Start_Hook_Type") or ""
    end_hook = _read(doc, rebar_id, "NOSA_Rebar_End_Hook_Type") or ""
    layer = _read(doc, rebar_id, "NOSA_Rebar_Layer") or "uncategorized"
    host_id = _read(doc, rebar_id, "NOSA_Rebar_Host_Element_Id")
    
    shape_params_tuple = _parse_shape_params(shape_params_str, tolerance_mm)
    
    # number_scope: "per_host" (por defecto), "per_project", "per_view"
    marking_cfg = std.get("marking", {}) if std else {}
    number_scope = marking_cfg.get("number_scope", "per_host")
    
    if number_scope == "per_project":
        host_key = None  # Todas las barras del proyecto comparten numeración
    elif number_scope == "per_view":
        host_key = None  # Por ahora, tratar como per_project (view requiere contexto de vista)
    else:  # per_host
        host_key = host_id
    
    return (bar_type_id, shape_code, shape_params_tuple, start_hook, end_hook, layer, host_key)


_HOST_CODES = (('OST_StructuralFraming', u'B'), ('OST_StructuralColumns', u'C'),
               ('OST_Walls', u'W'), ('OST_StructuralFoundation', u'F'), ('OST_Floors', u'S'))


def _host_code(host_elem):
    """One-letter host category code for marks of hosts that have no Mark."""
    try:
        from Autodesk.Revit import DB  # Lazy import
        from nosa_utils.revit_helpers import get_id_value
        cat_value = get_id_value(host_elem.Category.Id)
        for bic_name, code in _HOST_CODES:
            if cat_value == int(getattr(DB.BuiltInCategory, bic_name)):
                return code
    except Exception:
        pass
    return u'H'


def deduplicate_and_mark(doc, rebars, ctx):
    """
    Agrupa 'rebars' (lista de Rebar ElementIds) por posición según tolerancia.
    Asigna NOSA_Rebar_Mark, NOSA_Rebar_Number, NOSA_Rebar_Position_In_Host.
    
    Devuelve dict summary {total_positions: int, total_bars: int, largest_cluster: int}.
    """
    std = ctx.get("standard")
    marking_cfg = std.get("marking", {}) if std else {}
    tolerance_mm = marking_cfg.get("dedup_tolerance_mm", 5.0)
    mark_format = marking_cfg.get("mark_format", "{host_mark}-{number:02d}")
    prefix = ctx.get("mark_prefix", "") or ""
    hosts_without_mark = set()
    
    # Agrupar barras por clave de deduplicación
    clusters = {}
    for rebar_id in rebars:
        key = _get_dedup_key(doc, rebar_id, std, tolerance_mm)
        if key not in clusters:
            clusters[key] = []
        clusters[key].append(rebar_id)
    
    # Ordenar clusters por (layer, diámetro desc, primer parámetro A desc)
    # Para orden estable, extraer info del primer elemento de cada cluster
    def cluster_sort_key(kv):
        key, ids = kv
        if not ids:
            return ("", 0, 0)
        
        first_id = ids[0]
        layer = _read(doc, first_id, "NOSA_Rebar_Layer") or "zzz"
        rebar = doc.GetElement(first_id)
        if rebar:
            bar_type = doc.GetElement(rebar.GetTypeId())
            if bar_type:
                try:
                    diameter_mm = bar_type.BarModelDiameter * _FT_TO_MM
                except AttributeError:
                    try:
                        diameter_mm = bar_type.BarNominalDiameter * _FT_TO_MM
                    except AttributeError:
                        diameter_mm = 0.0
            else:
                diameter_mm = 0.0
        else:
            diameter_mm = 0.0
        
        # Primer parámetro A (si existe)
        shape_params_str = _read(doc, first_id, "NOSA_Rebar_Shape_Params") or ""
        first_param = 0.0
        if shape_params_str and 'A=' in shape_params_str:
            try:
                a_val = shape_params_str.split('A=')[1].split(';')[0]
                first_param = float(a_val.strip())
            except (IndexError, ValueError):
                pass
        
        return (layer, -diameter_mm, -first_param)
    
    sorted_clusters = sorted(clusters.items(), key=cluster_sort_key)
    
    # Asignar números correlativos
    position_number = 1
    total_bars = 0
    largest_cluster = 0
    
    for key, ids in sorted_clusters:
        if not ids:
            continue
        
        cluster_size = len(ids)
        total_bars += cluster_size
        if cluster_size > largest_cluster:
            largest_cluster = cluster_size
        
        # Obtener host_mark del primer elemento
        first_id = ids[0]
        host_id = _read(doc, first_id, "NOSA_Rebar_Host_Element_Id")
        if not host_id:
            try:
                from nosa_utils.revit_helpers import get_id_value  # Lazy: imports the Revit API
                host_id = u'{}'.format(get_id_value(doc.GetElement(first_id).GetHostId()))
            except Exception:
                host_id = None
        host_mark = ""
        host_elem = None
        if host_id:
            try:
                from Autodesk.Revit import DB  # Lazy import
                host_elem = doc.GetElement(DB.ElementId(int(host_id)))
                if host_elem:
                    host_mark_param = host_elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                    if host_mark_param and host_mark_param.HasValue:
                        host_mark = host_mark_param.AsString() or ""
            except Exception:
                host_elem = None
        if not host_mark:
            # Host without a Mark (T2.12): a bare "-01" repeats across hosts, so
            # use a category letter + the element id, e.g. "B1318407-01".
            host_mark = u'{}{}'.format(_host_code(host_elem), host_id or u'')
            hosts_without_mark.add(host_id)
        
        # Leer layer del primer elemento
        layer_key = _read(doc, first_id, "NOSA_Rebar_Layer") or "uncategorized"
        layer_name = marking_cfg.get("layer_names", {}).get(layer_key, layer_key)
        
        # Leer diámetro
        rebar = doc.GetElement(first_id)
        diameter_mm = 0.0
        if rebar:
            bar_type = doc.GetElement(rebar.GetTypeId())
            if bar_type:
                try:
                    diameter_mm = bar_type.BarModelDiameter * _FT_TO_MM
                except AttributeError:
                    try:
                        diameter_mm = bar_type.BarNominalDiameter * _FT_TO_MM
                    except AttributeError:
                        pass
        
        # Formatear marca
        try:
            mark = mark_format.format(
                host_mark=host_mark,
                number=position_number,
                diameter=int(diameter_mm),
                layer=layer_name,
                prefix=prefix
            )
        except (KeyError, ValueError):
            # Fallback si el formato falla
            mark = "{}-{:02d}".format(host_mark or "?", position_number)
        if prefix and "{prefix}" not in mark_format:
            mark = prefix + mark
        
        # Asignar a todas las barras del cluster
        for pos_idx, rebar_id in enumerate(ids, start=1):
            _write(doc, rebar_id, "NOSA_Rebar_Mark", mark)
            _write(doc, rebar_id, "NOSA_Rebar_Number", position_number)
            _write(doc, rebar_id, "NOSA_Rebar_Position_In_Host", pos_idx)
        
        position_number += 1
    
    return {
        "total_positions": len(sorted_clusters),
        "total_bars": total_bars,
        "largest_cluster": largest_cluster,
        "hosts_without_mark": len(hosts_without_mark)
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


def renumber_batch(doc, batch_id, ctx):
    """
    Re-ejecuta deduplicate_and_mark + assign_layers_and_lengths sobre todas las barras del lote.
    Respeta Finalized=1 (no renumera barras finalizadas).
    Devuelve summary.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory  # Lazy import
    
    # Recolectar todas las Rebar del documento
    all_rebars = FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElementIds()
    
    # Filtrar por batch_id y Finalized != 1
    batch_rebars = []
    for rid in all_rebars:
        stored_batch = _read(doc, rid, "NOSA_Rebar_Batch_Id")
        finalized = _read(doc, rid, "NOSA_Rebar_Finalized")
        
        if stored_batch == batch_id and finalized != 1 and finalized != "1":
            batch_rebars.append(rid)
    
    if not batch_rebars:
        return {"total_positions": 0, "total_bars": 0, "largest_cluster": 0}
    
    # Re-marcar
    assign_layers_and_lengths(doc, batch_rebars, ctx)
    summary = deduplicate_and_mark(doc, batch_rebars, ctx)
    
    return summary
