# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Bar Bending Schedule (BBS) generation and export.
Blueprint Parte 9 (F5).

Recolecta barras, agrupa por posición, calcula longitudes de corte, exporta CSV/XLSX.
"""
from __future__ import absolute_import, print_function, unicode_literals
import sys
import os

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
        
        filtered.append(rid)
    
    return filtered


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


def group_by_position(doc, rebar_ids):
    """
    Agrupa barras por NOSA_Rebar_Mark (posición).
    
    Returns:
        dict[mark_str, SchedulePosition]
    """
    positions = {}
    
    for rid in rebar_ids:
        mark = _read(doc, rid, "NOSA_Rebar_Mark")
        if not mark:
            mark = u"?"
        
        if mark not in positions:
            pos = SchedulePosition(mark)
            positions[mark] = pos
            
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
                    pass
        
        rebar = doc.GetElement(rid)
        positions[mark].add_bar(rid, _bar_quantity(rebar))
        import rebar_bending
        try:
            bars = rebar_bending.bar_variants(rebar, positions[mark].diameter_mm)
        except Exception:
            bars = []
        positions[mark].add_variants(bars)
    
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
        total_mm = var['count'] * var['unit_length_mm']
        rows.append({
            'mark': pos.mark + rebar_marking.variant_suffix(k),
            'group': pos.mark,
            'host_mark': pos.host_mark,
            'layer': pos.layer,
            'diameter_mm': pos.diameter_mm,
            'shape_code': pos.shape_code,
            'shape_params': pos.shape_params,
            'count': var['count'],
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
    for mark in sorted(positions.keys()):
        pos = positions[mark]
        weight_kg = (pos.total_length_mm / 1000.0) * mass_per_length_kg_m(pos.diameter_mm)
        if len(pos.variants) > 1:
            schedule.extend(_variant_rows(pos))
            continue
        schedule.append({
            'mark': pos.mark,
            'host_mark': pos.host_mark,
            'layer': pos.layer,
            'diameter_mm': pos.diameter_mm,
            'shape_code': pos.shape_code,
            'shape_params': pos.shape_params,
            'count': pos.count,
            'unit_length_mm': pos.unit_length_mm,
            'total_length_mm': pos.total_length_mm,
            'total_weight_kg': weight_kg,
            'unit_weight_kg': (pos.unit_length_mm / 1000.0) * mass_per_length_kg_m(pos.diameter_mm),
            'legs': pos.legs,
            'mandrel_mm': pos.mandrel_mm,
        })

    return schedule


def export_csv(schedule_data, output_path):
    """
    Exporta schedule_data a CSV.
    
    Args:
        schedule_data: list[dict] de generate_schedule_data()
        output_path: path completo del archivo CSV a crear
    
    Returns:
        True si éxito, False si error
    """
    try:
        # Python 3: modo texto con encoding UTF-8
        # Python 2 (IronPython): modo binario
        try:
            # Python 3
            import io
            f = io.open(output_path, 'w', encoding='utf-8', newline='')
            py3_mode = True
        except (AttributeError, TypeError):
            # Python 2 / IronPython
            f = open(output_path, 'wb')
            py3_mode = False
        
        try:
            # Cabeceras
            fieldnames = [
                'mark', 'host_mark', 'layer', 'diameter_mm', 'shape_code',
                'shape_params', 'count', 'unit_length_mm', 'total_length_mm',
                'total_weight_kg'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator='\n')
            
            # Escribir cabecera
            writer.writerow({fn: fn for fn in fieldnames})
            
            # Escribir datos
            for row in schedule_data:
                if py3_mode:
                    # Python 3: strings directamente
                    writer.writerow(row)
                else:
                    # Python 2: convertir unicode a UTF-8 bytes
                    encoded_row = {}
                    for key, val in row.items():
                        if isinstance(val, text_type):
                            encoded_row[key] = val.encode('utf-8')
                        else:
                            encoded_row[key] = str(val).encode('utf-8') if val else b''
                    writer.writerow(encoded_row)
        finally:
            f.close()
        
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
                    pass
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
