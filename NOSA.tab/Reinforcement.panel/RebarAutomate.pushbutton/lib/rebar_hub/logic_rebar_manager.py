# -*- coding: utf-8 -*-
import os
import sys
from Autodesk.Revit import DB
import re

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value, element_name, element_id_from_int
from nosa_utils import unit_conversion as _uc10
from nosa_utils.rebar_read import read_rebar
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarhub'


_FT_TO_MM = _uc10.FT_TO_MM

# BS 8666 shape codes mapped to letters A-E meaning
# Shape code: (description, dims_needed)
BS8666_SHAPES = {
    '00': (u'Straight', ['A']),
    '11': (u'L-bar',    ['A', 'B']),
    '12': (u'L-bar cranked', ['A', 'B']),
    '13': (u'Cranked',  ['A', 'B', 'C']),
    '21': (u'U-bar',    ['A', 'B']),
    '25': (u'Stirrup rectangular', ['A', 'B']),
    '26': (u'Stirrup square',      ['A']),
    '31': (u'S-bar',    ['A', 'B', 'C']),
    '32': (u'Z-bar',    ['A', 'B', 'C']),
    '33': (u'Bent bar', ['A', 'B', 'C', 'D']),
    '34': (u'Bent bar', ['A', 'B', 'C', 'D', 'E']),
    '41': (u'T-bar',    ['A', 'B', 'C']),
    '44': (u'T-bar welded', ['A', 'B', 'C']),
    '51': (u'Helical',  ['A', 'B']),
    '60': (u'Circular', ['A']),
    '63': (u'U-truss',  ['A', 'B', 'C']),
    '64': (u'U-truss cranked', ['A', 'B', 'C', 'D']),
    '98': (u'Fabric',   []),
    '99': (u'Defined by designer', []),
}

# Steel density kg/m³
STEEL_DENSITY = 7850.0

# Diameter → mass per metre (kg/m) per BS 8666
BAR_MASS_PER_M = {
    6:   0.222,  8:  0.395, 10: 0.617, 12: 0.888,
    16:  1.579,  20: 2.466, 25: 3.854, 32: 6.313,
    40: 9.864,   50: 15.41,
}


def _safe_double(param):
    try:
        if param and param.HasValue and param.StorageType == DB.StorageType.Double:
            return param.AsDouble()
    except Exception:
        log_swallowed(_LOG, u'_safe_double')
    return 0.0


def _safe_int(param):
    try:
        if param and param.HasValue and param.StorageType == DB.StorageType.Integer:
            return param.AsInteger()
    except Exception:
        log_swallowed(_LOG, u'_safe_int')
    return 0


def _safe_str(param):
    try:
        if param and param.HasValue and param.StorageType == DB.StorageType.String:
            v = param.AsString()
            return v or u''
    except Exception:
        log_swallowed(_LOG, u'_safe_str')
    return u''


def _mm(internal_feet):
    return internal_feet * _FT_TO_MM


def _get_rebar_class():
    """Return Rebar class, trying multiple namespace paths for Revit 2024–2027."""
    for path in [
        'Autodesk.Revit.DB.Structure.Rebar',
        'Autodesk.Revit.DB.Rebar',
    ]:
        try:
            parts = path.rsplit('.', 1)
            ns, cls = parts[0], parts[1]
            mod = __import__(ns, fromlist=[cls])
            return getattr(mod, cls)
        except Exception:
            log_swallowed(_LOG, u'_get_rebar_class')
    return None


def collect_rebar(doc, view_id=None):
    """Every rebar in the model (or view) as plain dicts — nosa_utils.rebar_read.read_rebar."""
    RebarClass = _get_rebar_class()
    if RebarClass is None:
        return []
    try:
        col = (DB.FilteredElementCollector(doc, view_id) if view_id else DB.FilteredElementCollector(doc)) \
            .OfClass(RebarClass).ToElements()
    except Exception:
        log_swallowed(_LOG, u'collect_rebar.collector')
        return []

    results = []
    for rb in col:
        try:
            r = read_rebar(doc, rb)
        except Exception:
            log_swallowed(_LOG, u'collect_rebar.read_rebar')
            continue
        shape = (r['shape'] or u'99').split()[0]
        results.append({
            'id':          r['id'],
            'mark':        r['mark'] or u'—',
            'partition':   r['partition'],
            'diameter':    r['diameter'],
            'diameter_label': u'H{}'.format(r['diameter']),
            'quantity':    r['quantity'] * r['members'],
            'length_mm':   r['bar_length_mm'],
            'shape':       shape,
            'shape_desc':  BS8666_SHAPES.get(shape, (u'Custom', []))[0],
            'host':        u' '.join(x for x in (r['host_category'], r['host_mark']) if x),
            'level':       r['level'],
            'total_len_m': round(r['total_length_mm'] * r['members'] / 1000.0, 3),
            'mass_kg':     round(r['mass_kg'], 2),
        })
    return results


def _group_key(bar):
    """Marks are per partition (BS 8666): the same 01 in two partitions are different bars."""
    return (bar.get('partition') or u'', bar['mark'])


def group_by_mark(bars):
    """Group bars by (partition, mark). Returns dict: key -> aggregated dict."""
    groups = {}
    for b in bars:
        key = _group_key(b)
        if key not in groups:
            groups[key] = {
                'mark':       u'{} / {}'.format(key[0], key[1]) if key[0] else key[1],
                'diameter':   b['diameter'],
                'diameter_label': b['diameter_label'],
                'shape':      b['shape'],
                'shape_desc': b['shape_desc'],
                'length_mm':  b['length_mm'],
                'quantity':   0,
                'total_len_m': 0.0,
                'mass_kg':    0.0,
                'levels':     set(),
                'hosts':      set(),
            }
        g = groups[key]
        g['quantity']    += b['quantity']
        g['total_len_m'] += b['total_len_m']
        g['mass_kg']     += b['mass_kg']
        g['levels'].add(b['level'])
        g['hosts'].add(b['host'])

    for g in groups.values():
        g['levels'] = u', '.join(sorted(x for x in g['levels'] if x))
        g['hosts']  = u', '.join(sorted(x for x in g['hosts'] if x))
        g['total_len_m'] = round(float(g['total_len_m']), 2)
        g['mass_kg']     = round(float(g['mass_kg']), 2)

    return groups


def detect_duplicate_marks(bars):
    """Return list of marks where multiple distinct diameters exist — likely errors."""
    mark_diams = {}
    for b in bars:
        key = _group_key(b)
        m = u'{} / {}'.format(key[0], key[1]) if key[0] else key[1]
        mark_diams.setdefault(m, set()).add(b['diameter'])
    return {m: diams for m, diams in mark_diams.items() if len(diams) > 1}


def renumber_marks(doc, bars, prefix, start_num):
    """Reassign bar Mark parameter sequentially: {prefix}{n}."""
    # Group unique old marks → new mark
    old_marks = sorted(set(b['mark'] for b in bars), key=lambda x: x)
    mapping   = {}
    for i, old in enumerate(old_marks):
        mapping[old] = u'{}{}'.format(prefix, start_num + i)

    changed = 0
    for b in bars:
        el = doc.GetElement(element_id_from_int(b['id']))
        if el is None:
            continue
        new_mark = mapping.get(b['mark'])
        if new_mark is None:
            continue
        # the BS mark lives in Schedule Mark (RebarAutomate) and NOSA_Rebar_Mark
        wrote = False
        for p in (el.get_Parameter(DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK),
                  el.LookupParameter('NOSA_Rebar_Mark')):
            if p is not None and not p.IsReadOnly:
                p.Set(new_mark)
                wrote = True
        changed += 1 if wrote else 0

    return changed, mapping


def export_bs8666_excel(bars_grouped, filepath, project_no=u'', rev=u'P01'):
    """Export to Excel in BS 8666 schedule format."""
    try:
        import openpyxl
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = u'BS 8666 Schedule'

        ORANGE = 'FFFF5F00'
        LGREY  = 'FFF5F5F5'
        WHITE  = 'FFFFFFFF'
        BLACK  = 'FF000000'

        hdr_fill  = PatternFill('solid', fgColor=ORANGE)
        hdr_font  = Font(bold=True, color='FFFFFFFF', name='Calibri', size=10)
        body_font = Font(name='Calibri', size=10)
        c_align   = Alignment(horizontal='center', vertical='center')
        l_align   = Alignment(horizontal='left',   vertical='center')
        thin      = Side(border_style='thin', color=BLACK)
        border    = Border(left=thin, right=thin, top=thin, bottom=thin)

        # Title rows
        ws['A1'] = u'NOSA Engineering — Reinforcement Bar Bending Schedule'
        ws['A1'].font = Font(bold=True, size=12, name='Calibri')
        ws['A2'] = u'Project: {}    Rev: {}'.format(project_no, rev)
        ws['A2'].font = Font(size=10, name='Calibri')
        ws.merge_cells('A1:L1')
        ws.merge_cells('A2:L2')

        # Header row (row 4)
        headers = ['Bar Mark', 'Type & Size', 'No. of Mbrs', 'No. in Each',
                   'Total No.', 'Length of Each (mm)', 'Shape Code',
                   'A (mm)', 'B (mm)', 'C (mm)', 'D (mm)', 'Total Mass (kg)']
        widths  = [12, 12, 12, 10, 10, 18, 12, 10, 10, 10, 10, 14]

        for col_idx, (h, w) in enumerate(zip(headers, widths), 1):
            cell = ws.cell(row=4, column=col_idx, value=h)
            cell.fill   = hdr_fill
            cell.font   = hdr_font
            cell.alignment = c_align
            cell.border = border
            ws.column_dimensions[ws.cell(row=4, column=col_idx).column_letter].width = w

        # Data rows
        row_num = 5
        sorted_groups = sorted(bars_grouped.values(), key=lambda g: g['mark'])
        for g in sorted_groups:
            fill = PatternFill('solid', fgColor=LGREY) if row_num % 2 == 0 else PatternFill('solid', fgColor=WHITE)
            vals = [
                g['mark'],
                g['diameter_label'],
                u'1',
                str(g['quantity']),
                str(g['quantity']),
                u'{:.0f}'.format(g.get('length_mm', g['total_len_m'] * 1000 / max(g['quantity'],1))),
                g['shape'],
                u'', u'', u'', u'',
                u'{:.2f}'.format(g['mass_kg']),
            ]
            for col_idx, v in enumerate(vals, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=v)
                cell.font      = body_font
                cell.fill      = fill
                cell.border    = border
                cell.alignment = c_align if col_idx != 1 else l_align
            row_num += 1

        # Totals row
        ws.cell(row=row_num, column=1, value=u'TOTAL').font = Font(bold=True, name='Calibri')
        total_mass = sum(g['mass_kg'] for g in bars_grouped.values())
        tc = ws.cell(row=row_num, column=12, value=u'{:.2f}'.format(total_mass))
        tc.font   = Font(bold=True, name='Calibri')
        tc.border = border

        wb.save(filepath)
        return True, None
    except Exception as e:
        return False, str(e)
