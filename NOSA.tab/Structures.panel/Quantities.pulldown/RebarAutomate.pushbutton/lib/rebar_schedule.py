# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Bar Bending Schedule (BBS) generation and export.
Blueprint Parte 9 (F5).

Recolecta barras, agrupa por posición, calcula longitudes de corte, exporta CSV/XLSX.
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys
import os
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils import shared_params
from nosa_utils.compat import text_type
import csv

_FT_TO_MM = 304.8


# BUG FIX (2026-09-02) — same signature mismatch found in rebar_marking.py
# and rebar_shape_classifier.py: every read in this file called
# shared_params.read(doc, rid, name), but the real signature is
# read(elem, guid_or_name, default=None) — no `doc` at all. This one is
# the WORST of the three: read() never raises (it's designed not to), so
# `doc` silently failed to resolve as `elem`, and the field NAME string
# ("NOSA_Rebar_Batch_Id" etc.) got bound to the `default` parameter —
# every read here SILENTLY returned its own field name as if it were the
# real value, never None or empty. Concretely: `stored_batch` was always
# the truthy string "NOSA_Rebar_Batch_Id" (never empty), so `collect_
# rebars`'s "is this a NOSA bar" filter never excluded anything (EVERY
# Rebar in the document was treated as a NOSA bar), and a batch_id filter
# always excluded EVERYTHING (stored_batch could never equal a real
# batch_id) — the schedule/BBS export (F5) has been reading garbage since
# it was written.
def _read(doc, rebar_id, name, default=None):
    elem = doc.GetElement(rebar_id)
    if elem is None:
        return default
    return shared_params.read(elem, name, default)


def mass_per_length_kg_m(diameter_mm):
    """
    Nominal steel rebar mass per metre, kg/m — the universal
    density-and-cross-section formula (mass_per_m = pi/4 * d^2 * rho,
    rho = 7850 kg/m^3 for structural steel), NOT tied to any one
    normative code (EHE-08/BS-8666/EN-ISO's own steel.mass_per_length_
    kg_m tables in data/rebar_standards/*.json all match this formula
    to within rounding — e.g. it gives 1.580 kg/m for a 16mm bar,
    EHE-08's own table says 1.578). Used here instead of threading a
    `std` object through the schedule module purely for this one
    figure — every normative code agrees on it, it's just physics.

    Matches SOFiSTiK Reinforcement's own "Rebar Weight Schedule" output
    (Total Weight [kg] column) — see the reference flyer this feature
    was modelled on.
    """
    return (diameter_mm ** 2) / 162.0


class SchedulePosition(object):
    """Representa una posición (Mark) en el despiece, con todas sus barras."""
    
    def __init__(self, mark):
        self.mark = mark
        self.bars = []  # lista de ElementIds
        self.diameter_mm = 0
        self.shape_code = u''
        self.shape_params = u''
        self.count = 0
        self.unit_length_mm = 0.0
        self.total_length_mm = 0.0
        self.layer = u''
        self.host_mark = u''
        self.member = u''
        self.members = 1
        self.legs = None
        self.mandrel_mm = None
        self.variants = {}
    
    def add_bar(self, rebar_id, quantity=1):
        """Añade un elemento Rebar (un Rebar Set aporta todas sus barras)."""
        self.bars.append(rebar_id)
        self.count += quantity
    
    def add_variants(self, bars):
        """Tally each bar's bending geometry; bars with equal legs share one variant."""
        for geometry, length_mm in bars:
            import rebar_bending
            key = rebar_bending.variant_key(geometry, length_mm)
            var = self.variants.get(key)
            if var is None:
                self.variants[key] = var = {
                    'legs': geometry['legs'] if geometry else None,
                    'mandrel_mm': geometry['mandrel_mm'] if geometry else None,
                    'count': 0, 'unit_length_mm': length_mm}
            var['count'] += 1
        if self.variants:
            first = max(self.variants.values(), key=lambda v: v['count'])
            self.legs, self.mandrel_mm = first['legs'], first['mandrel_mm']

    def compute_totals(self):
        """Calcula longitudes totales (count × unit_length)."""
        self.total_length_mm = self.count * self.unit_length_mm


def collect_rebars(doc, batch_id=None, include_finalized=False):
    """
    Recolecta todas las barras del documento (o de un lote específico).
    
    Args:
        doc: Revit Document
        batch_id: opcional, filtra por batch_id (None = todas las barras NOSA)
        include_finalized: si False, excluye barras con Finalized=1
    
    Returns:
        list[ElementId] de barras filtradas
    """
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
    
    # Recolectar todas las Rebar
    all_rebars = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Rebar
    ).WhereElementIsNotElementType().ToElementIds()
    
    filtered = []
    for rid in all_rebars:
        # Verificar que tenga NOSA_Rebar_Batch_Id (es una barra NOSA)
        stored_batch = _read(doc, rid, "NOSA_Rebar_Batch_Id")
        if not stored_batch:
            continue
        
        # Filtrar por batch_id si se especificó
        if batch_id and stored_batch != batch_id:
            continue
        
        # Filtrar finalizadas si no se incluyen
        if not include_finalized:
            finalized = _read(doc, rid, "NOSA_Rebar_Finalized")
            if finalized == 1 or finalized == "1":
                continue

        # Partitions tool: a copy of an identical member is counted through the
        # representative's 'No. of mbrs' — only an explicit No leaves the schedule
        if not shows_in_schedule(doc.GetElement(rid)):
            continue

        filtered.append(rid)
    
    return filtered


def shows_in_schedule(rebar):
    """False only when NOSA_Rebar_Show_In_Schedule is explicitly No (never written = shown)."""
    try:
        param = rebar.LookupParameter("NOSA_Rebar_Show_In_Schedule")
        return not (param is not None and param.HasValue and param.AsInteger() == 0)
    except Exception:
        return True


def members_of(rebar):
    """BBS 'No. of mbrs': the template's Number of Members (1 when absent or empty)."""
    try:
        param = rebar.LookupParameter("Number of Members")
        if param is not None and param.HasValue:
            value = param.AsDouble() if param.StorageType.ToString() == 'Double' else param.AsInteger()
            return max(1, int(round(value)))
    except Exception:
        log_swallowed(_LOG, u'members_of')
    return 1


def _bar_quantity(rebar):
    """Bars in one Rebar element: a Rebar Set holds Quantity bars (T4.1)."""
    try:
        return max(1, int(rebar.Quantity))
    except Exception:
        return 1


def _unit_length_mm(rebar):
    """Cut length of ONE bar; Rebar.TotalLength covers the whole set."""
    import rebar_bending
    return rebar_bending.unit_cut_length_mm(rebar)


def _partition_of(rebar):
    """The bar's native Partition (the BBS Member), '' when unset."""
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        return rebar.get_Parameter(BuiltInParameter.NUMBER_PARTITION_PARAM).AsString() or u''
    except Exception:
        return u''


def group_by_position(doc, rebar_ids):
    """
    Group bars by (partition, NOSA_Rebar_Mark): marks restart at 01 in every partition.

    Returns:
        dict[(member, mark), SchedulePosition]
    """
    positions = {}

    for rid in rebar_ids:
        mark = _read(doc, rid, "NOSA_Rebar_Mark")
        if not mark:
            mark = u"?"
        key = (_partition_of(doc.GetElement(rid)), mark)

        if key not in positions:
            pos = SchedulePosition(mark)
            pos.member = key[0]
            positions[key] = pos
            
            # Leer datos comunes de la primera barra de esta posición
            rebar = doc.GetElement(rid)
            if rebar:
                bar_type = doc.GetElement(rebar.GetTypeId())
                if bar_type:
                    # Nominal diameter, rounded: int(BarModelDiameter) gave H8 -> 7 (T4.1).
                    try:
                        pos.diameter_mm = int(round(bar_type.BarNominalDiameter * _FT_TO_MM))
                    except AttributeError:
                        try:
                            pos.diameter_mm = int(round(bar_type.BarModelDiameter * _FT_TO_MM))
                        except AttributeError:
                            pos.diameter_mm = 0
            
            pos.shape_code = _read(doc, rid, "NOSA_Rebar_Shape_Code") or u"99"
            pos.shape_params = _read(doc, rid, "NOSA_Rebar_Shape_Params") or u""
            pos.layer = _read(doc, rid, "NOSA_Rebar_Layer") or u""
            pos.unit_length_mm = _unit_length_mm(rebar)
            
            # Host mark
            host_id = _read(doc, rid, "NOSA_Rebar_Host_Element_Id")
            if host_id:
                try:
                    from Autodesk.Revit.DB import BuiltInParameter
                    from nosa_utils.revit_helpers import element_id_from_int
                    host = doc.GetElement(element_id_from_int(host_id))
                    if host:
                        mark_param = host.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
                        if mark_param and mark_param.HasValue:
                            pos.host_mark = mark_param.AsString() or u""
                except:
                    log_swallowed(_LOG, u'group_by_position')
        
        rebar = doc.GetElement(rid)
        positions[key].add_bar(rid, _bar_quantity(rebar))
        positions[key].members = max(getattr(positions[key], 'members', 1), members_of(rebar))
        import rebar_bending
        try:
            bars = rebar_bending.bar_variants(rebar, positions[key].diameter_mm)
        except Exception:
            bars = []
        positions[key].add_variants(bars)
    
    # Calcular totales para todas las posiciones
    for pos in positions.values():
        pos.compute_totals()
    
    return positions


def _variant_rows(pos):
    """A varying set: one row per bar length, marks 05A, 05B ... (BS 8666, T4.2)."""
    import rebar_marking
    rows = []
    variants = sorted(pos.variants.values(), key=lambda v: v['unit_length_mm'])
    for k, var in enumerate(variants):
        total_mm = var['count'] * var['unit_length_mm'] * pos.members
        rows.append({
            'mark': pos.mark + rebar_marking.variant_suffix(k),
            'group': pos.mark,
            'host_mark': pos.host_mark,
            'member': pos.member,
            'layer': pos.layer,
            'diameter_mm': pos.diameter_mm,
            'shape_code': pos.shape_code,
            'shape_params': pos.shape_params,
            'count': var['count'],
            'members': pos.members,
            'unit_length_mm': var['unit_length_mm'],
            'total_length_mm': total_mm,
            'total_weight_kg': (total_mm / 1000.0) * mass_per_length_kg_m(pos.diameter_mm),
            'unit_weight_kg': (var['unit_length_mm'] / 1000.0) * mass_per_length_kg_m(pos.diameter_mm),
            'legs': var['legs'],
            'mandrel_mm': var['mandrel_mm'],
        })
    return rows


def generate_schedule_data(doc, batch_id=None, include_finalized=False):
    """
    Genera datos completos del despiece.
    
    Returns:
        list[dict] con una entrada por posición, campos:
        - mark, host_mark, layer, diameter_mm, shape_code, shape_params,
          count, unit_length_mm, total_length_mm, total_weight_kg
    """
    rebars = collect_rebars(doc, batch_id, include_finalized)
    positions = group_by_position(doc, rebars)

    # Convertir a lista de dicts, ordenada por mark
    schedule = []
    for key in sorted(positions.keys()):
        pos = positions[key]
        total_mm = pos.total_length_mm * pos.members
        weight_kg = (total_mm / 1000.0) * mass_per_length_kg_m(pos.diameter_mm)
        if len(pos.variants) > 1:
            schedule.extend(_variant_rows(pos))
            continue
        schedule.append({
            'mark': pos.mark,
            'host_mark': pos.host_mark,
            'member': pos.member,
            'layer': pos.layer,
            'diameter_mm': pos.diameter_mm,
            'shape_code': pos.shape_code,
            'shape_params': pos.shape_params,
            'count': pos.count,
            'members': pos.members,
            'unit_length_mm': pos.unit_length_mm,
            'total_length_mm': total_mm,
            'total_weight_kg': weight_kg,
            'unit_weight_kg': (pos.unit_length_mm / 1000.0) * mass_per_length_kg_m(pos.diameter_mm),
            'legs': pos.legs,
            'mandrel_mm': pos.mandrel_mm,
        })

    return schedule


BBS_COLUMNS = (u'Member', u'Bar mark', u'Type and size', u'No. of mbrs', u'No. of bars in each',
               u'Total no.', u'Length of each bar (mm)', u'Shape code', u'A', u'B', u'C', u'D',
               u'E', u'r', u'Weight (kg)')


def _shape_dims(shape_params):
    """'A=605;B=210;C=605;R=24' -> {'A': '605', ...} (R reported as BS 8666 r)."""
    dims = {}
    for part in (shape_params or u'').split(u';'):
        if u'=' in part:
            key, value = part.split(u'=', 1)
            dims[key.strip().upper()] = value.strip()
    return dims


def bbs_rows(schedule_data):
    """Schedule rows in BS 8666:2020 column order (strings), one per bar mark."""
    rows = []
    for row in schedule_data:
        dims = _shape_dims(row.get('shape_params'))
        count = int(row.get('count') or 0)
        members = max(1, int(row.get('members') or 1))
        rows.append([
            row.get('member') or u'',
            row.get('mark') or u'',
            u'H{}'.format(int(row.get('diameter_mm') or 0)),
            text_type(members), text_type(count), text_type(members * count),
            text_type(int(round(row.get('unit_length_mm') or 0))),
            row.get('shape_code') or u'',
            dims.get(u'A', u''), dims.get(u'B', u''), dims.get(u'C', u''),
            dims.get(u'D', u''), dims.get(u'E', u''), dims.get(u'R', u''),
            u'{:.1f}'.format(row.get('total_weight_kg') or 0.0),
        ])
    return rows


def _csv_cell(value):
    value = text_type(value)
    if any(ch in value for ch in (u',', u'"', u'\n')):
        value = u'"' + value.replace(u'"', u'""') + u'"'
    return value


def export_csv(schedule_data, output_path):
    """Write the bar bending schedule as CSV in BS 8666:2020 columns; True on success."""
    import io
    try:
        with io.open(output_path, 'w', encoding='utf-8', newline='') as f:
            f.write(u'\ufeff')   # one BOM so Excel reads UTF-8 (utf-8-sig repeats it per write in IronPython)
            for cells in [list(BBS_COLUMNS)] + bbs_rows(schedule_data):
                f.write(u','.join(_csv_cell(c) for c in cells) + u'\r\n')
        return True
    except Exception as e:
        print(u'[rebar_schedule] CSV export failed: {}'.format(e))
        return False


def export_xlsx(schedule_data, output_path):
    """
    Exporta schedule_data a XLSX (Excel).
    Requiere openpyxl (pip install openpyxl) — si no está disponible, retorna False.
    
    Args:
        schedule_data: list[dict] de generate_schedule_data()
        output_path: path completo del archivo XLSX a crear
    
    Returns:
        True si éxito, False si error o librería no disponible
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        print(u'[rebar_schedule] openpyxl not available, XLSX export skipped')
        return False
    
    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Bar Bending Schedule"
        
        # Cabeceras (en inglés británico)
        headers = [
            'Mark', 'Host', 'Layer', 'Diameter (mm)', 'Shape Code',
            'Shape Parameters', 'Quantity', 'Unit Length (mm)', 'Total Length (mm)',
            'Total Weight (kg)'
        ]
        ws.append(headers)

        # Datos
        for row in schedule_data:
            ws.append([
                row['mark'],
                row['host_mark'],
                row['layer'],
                row['diameter_mm'],
                row['shape_code'],
                row['shape_params'],
                row['count'],
                round(row['unit_length_mm'], 1),
                round(row['total_length_mm'], 1),
                round(row.get('total_weight_kg', 0.0), 2)
            ])
        
        # Formato: bold headers, auto-width
        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    log_swallowed(_LOG, u'export_xlsx')
            ws.column_dimensions[col_letter].width = min(max_length + 2, 50)

        # Second sheet — "Rebar Weight Schedule" summary by diameter,
        # matching SOFiSTiK Reinforcement's own summary sheet layout
        # (Sizes used / Number of Bars / Total Length / Total Weight,
        # plus a TOTALS row).
        stats = get_summary_stats(schedule_data)
        ws2 = wb.create_sheet(title=u'Weight Summary')
        ws2.append([u'Diameter (mm)', u'Number of Bars', u'Total Length (m)', u'Total Weight (kg)'])
        for dia in sorted(stats['by_diameter'].keys()):
            d = stats['by_diameter'][dia]
            ws2.append([dia, d['count'], round(d['length_m'], 2), round(d['weight_kg'], 2)])
        ws2.append([u'TOTALS', stats['total_bars'], stats['total_length_m'], stats['total_weight_kg']])
        for cell in ws2[1]:
            cell.font = cell.font.copy(bold=True)
        for cell in ws2[ws2.max_row]:
            cell.font = cell.font.copy(bold=True)
        for col in ws2.columns:
            max_length = max((len(str(c.value)) for c in col if c.value), default=0)
            ws2.column_dimensions[col[0].column_letter].width = min(max_length + 2, 30)

        wb.save(output_path)
        return True
    
    except Exception as e:
        print(u'[rebar_schedule] XLSX export failed: {}'.format(e))
        return False


def get_summary_stats(schedule_data):
    """
    Calcula estadísticas sumarias del despiece.
    
    Returns:
        dict con total_positions, total_bars, total_length_m,
        total_weight_kg, by_diameter (count/length_m/weight_kg cada uno)
        — mismo desglose que la "Rebar Weight Schedule" de SOFiSTiK
        Reinforcement (por diámetro + fila de totales).
    """
    total_positions = len(schedule_data)
    total_bars = sum(row['count'] for row in schedule_data)
    total_length_mm = sum(row['total_length_mm'] for row in schedule_data)
    total_length_m = total_length_mm / 1000.0
    total_weight_kg = sum(row.get('total_weight_kg', 0.0) for row in schedule_data)

    # Agrupar por diámetro
    by_diameter = {}
    for row in schedule_data:
        dia = row['diameter_mm']
        if dia not in by_diameter:
            by_diameter[dia] = {'count': 0, 'length_m': 0.0, 'weight_kg': 0.0}
        by_diameter[dia]['count'] += row['count']
        by_diameter[dia]['length_m'] += row['total_length_mm'] / 1000.0
        by_diameter[dia]['weight_kg'] += row.get('total_weight_kg', 0.0)

    return {
        'total_positions': total_positions,
        'total_bars': total_bars,
        'total_length_m': round(total_length_m, 2),
        'total_weight_kg': round(total_weight_kg, 2),
        'by_diameter': by_diameter
    }
