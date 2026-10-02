# -*- coding: utf-8 -*-
"""
Rebar Schedule Generator v1.0 — Logic

Collects all rebar from the model, groups by host element / diameter / shape,
computes quantities and weights, and provides Excel/CSV export.
"""
import math, io, csv
from collections import defaultdict
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.rebar_read import read_rebar
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarhub.schedule'
from nosa_utils import unit_conversion as _uc10
FT2MM  = _uc10.FT_TO_MM
FT2M   = _uc10.FT_TO_M

# ── weight table  (kg/m = 0.00617 × d²)  ────────────────────────────────────
def _weight_per_m(dia_mm):
    """Return weight per metre in kg/m for a given bar diameter."""
    if dia_mm and dia_mm > 0:
        return 0.006165 * dia_mm * dia_mm
    return 0.0


# ── host category mapping (lazy — DB.BuiltInCategory must not be at module level) ─
def _host_bic_labels():
    return {
        int(DB.BuiltInCategory.OST_StructuralColumns):    u'Column',
        int(DB.BuiltInCategory.OST_StructuralFraming):    u'Beam',
        int(DB.BuiltInCategory.OST_StructuralFoundation): u'Foundation',
        int(DB.BuiltInCategory.OST_Floors):               u'Slab',
        int(DB.BuiltInCategory.OST_Walls):                u'Wall',
    }

def _host_filter_options():
    return [
        (u'All categories',  None),
        (u'Columns',         int(DB.BuiltInCategory.OST_StructuralColumns)),
        (u'Beams',           int(DB.BuiltInCategory.OST_StructuralFraming)),
        (u'Foundations',     int(DB.BuiltInCategory.OST_StructuralFoundation)),
        (u'Slabs',           int(DB.BuiltInCategory.OST_Floors)),
        (u'Walls',           int(DB.BuiltInCategory.OST_Walls)),
    ]

def get_host_filter_names():
    return [o[0] for o in _host_filter_options()]

# Legacy name kept for callers that may use it
HOST_FILTER_NAMES = None  # populated lazily via get_host_filter_names()


# ── helpers ────────────────────────────────────────────────────────────────────



def _ps(el, bip, default=u''):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsString() or default
    except Exception:
        pass
    return default


def _pd(el, bip, default=0.0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            v = p.AsDouble()
            return v if v >= 0 else default
    except Exception:
        pass
    return default


def _pi(el, bip, default=0):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return p.AsInteger()
    except Exception:
        pass
    return default


def get_levels(doc):
    levels = sorted(
        DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
        key=lambda lv: lv.Elevation)
    return [(lv.Name, get_id_value(lv.Id)) for lv in levels]


def get_phases(doc):
    phases = list(DB.FilteredElementCollector(doc).OfClass(DB.Phase).ToElements())
    return [(ph.Name, get_id_value(ph.Id)) for ph in phases]


def _host_cat_label(host_el):
    if host_el is None:
        return u'Unknown'
    try:
        bic = get_id_value(host_el.Category.Id)
        return _host_bic_labels().get(bic, host_el.Category.Name or u'Other')
    except Exception:
        return u'Unknown'


def _host_mark(host_el):
    if host_el is None:
        return u'—'
    try:
        p = host_el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        if p and p.HasValue:
            return p.AsString() or u'—'
    except Exception:
        pass
    return u'—'


def _host_level(host_el, doc):
    if host_el is None:
        return u'—'
    for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM,
                DB.BuiltInParameter.WALL_BASE_CONSTRAINT]:
        try:
            p = host_el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv:
                    return lv.Name or u'—'
        except Exception:
            pass
    return u'—'


def _shape_name(rebar, doc):
    try:
        shape_id = rebar.GetShapeId()
        shape    = doc.GetElement(shape_id)
        if shape:
            return element_name(shape) or u'—'
    except Exception:
        pass
    return u'—'


def _bar_diameter_mm(rebar, doc):
    """Return nominal bar diameter in mm from the bar type."""
    try:
        bt = doc.GetElement(rebar.GetTypeId())
        if bt:
            for bip in [DB.BuiltInParameter.REBAR_BAR_DIAMETER,
                        DB.BuiltInParameter.REBAR_MODEL_BAR_DIAMETER_OF_DISTRIBUTED_REBAR]:
                p = bt.get_Parameter(bip)
                if p and p.HasValue:
                    d = p.AsDouble()
                    if d > 0:
                        return round(d * FT2MM, 1)
    except Exception:
        pass
    return None


def _bar_spacing_mm(rebar):
    """For area/path rebar, return spacing in mm (or None for individual bars)."""
    try:
        # RebarInSystem or area rebar spacing
        p = rebar.get_Parameter(DB.BuiltInParameter.REBAR_SPACING)
        if p and p.HasValue:
            s = p.AsDouble()
            if s > 0:
                return round(s * FT2MM, 1)
    except Exception:
        pass
    return None


def _n_bars(rebar):
    """Total number of physical bars represented by this rebar element."""
    try:
        return max(rebar.NumberOfBarPositions, 1)
    except Exception:
        pass
    try:
        n = _pi(rebar, DB.BuiltInParameter.REBAR_NUMBER_OF_SETS)
        return max(n, 1)
    except Exception:
        pass
    return 1


def _cut_length_mm(rebar):
    """Length of a single bar in mm."""
    for bip in [DB.BuiltInParameter.REBAR_ELEM_LENGTH_PER_TYPE,
                DB.BuiltInParameter.CURVE_ELEM_LENGTH]:
        try:
            p = rebar.get_Parameter(bip)
            if p and p.HasValue:
                v = p.AsDouble()
                if v > 0:
                    return round(v * FT2MM, 0)
        except Exception:
            pass
    try:
        lp = rebar.get_Parameter(DB.BuiltInParameter.REBAR_TOTAL_LENGTH_PER_TYPE)
        if lp and lp.HasValue:
            n = _n_bars(rebar)
            if n > 0:
                return round((lp.AsDouble() / n) * FT2MM, 0)
    except Exception:
        pass
    return None


def _bar_mark(rebar):
    """Bar mark / type mark for the schedule."""
    for bip in [DB.BuiltInParameter.ALL_MODEL_TYPE_MARK,
                DB.BuiltInParameter.ALL_MODEL_MARK]:
        v = _ps(rebar, bip)
        if v:
            return v
    return u'—'


# ── schedule row ──────────────────────────────────────────────────────────────

class ScheduleRow(object):
    __slots__ = ['group', 'host_cat', 'host_mark', 'host_level',
                 'bar_mark', 'shape', 'dia_mm', 'n_bars',
                 'cut_length_mm', 'total_length_m',
                 'wt_per_m', 'total_weight_kg',
                 'is_subtotal', 'el_ids']

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw.get(s, None))
        if self.el_ids is None:
            self.el_ids = []

    def add(self, n, cut_mm, total_m, wt_kg, el_id):
        self.n_bars          = (self.n_bars or 0) + n
        self.total_length_m  = (self.total_length_m  or 0.0) + total_m
        self.total_weight_kg = (self.total_weight_kg or 0.0) + wt_kg
        if el_id is not None:
            self.el_ids.append(el_id)

    # ── display strings ───────────────────────────────────────────────────────
    @property
    def host_cat_str(self):   return self.host_cat   or u'—'
    @property
    def host_mark_str(self):  return self.host_mark  or u'—'
    @property
    def host_level_str(self): return self.host_level or u'—'
    @property
    def bar_mark_str(self):   return self.bar_mark   or u'—'
    @property
    def shape_str(self):      return self.shape      or u'—'
    @property
    def dia_str(self):
        return u'φ{:.0f}'.format(self.dia_mm) if self.dia_mm else u'—'
    @property
    def n_bars_str(self):
        return str(self.n_bars or 0)
    @property
    def cut_str(self):
        return u'{:.0f}'.format(self.cut_length_mm) if self.cut_length_mm else u'—'
    @property
    def total_len_str(self):
        v = self.total_length_m or 0.0
        return u'{:.2f}'.format(v) if v > 0 else u'—'
    @property
    def wt_per_m_str(self):
        v = self.wt_per_m or 0.0
        return u'{:.3f}'.format(v) if v > 0 else u'—'
    @property
    def total_wt_str(self):
        v = self.total_weight_kg or 0.0
        if v <= 0:
            return u'—'
        if v >= 1000:
            return u'{:.3f} t'.format(v / 1000.0)
        return u'{:.1f} kg'.format(v)
    @property
    def group_str(self):      return self.group      or u''


# ── collection ────────────────────────────────────────────────────────────────

def collect_schedule(doc, options):
    """
    options = {
        'group_by':          'host' | 'diameter' | 'shape'
        'filter_host_bic':   int|None
        'filter_level_id':   int|None
        'filter_phase_id':   int|None   (exclude this phase)
        'show_subtotals':    bool
    }
    Returns (list_of_ScheduleRow, totals_ScheduleRow).
    """
    group_by       = options.get('group_by', 'host')
    filter_host    = options.get('filter_host_bic', None)
    filter_lv_id   = options.get('filter_level_id', None)
    filter_ph_id   = options.get('filter_phase_id', None)
    show_subtotals = options.get('show_subtotals', True)

    # DB.Structure is not an attribute until its namespace is imported (IronPython): it
    # returned no rows at all
    from Autodesk.Revit.DB.Structure import Rebar as _RebarClass

    rows_by_key = {}

    def _key(group, host_cat, host_mark, host_lv, bar_mark, shape, dia_mm, cut_mm):
        if group_by == 'host':
            g = u'{} — {}'.format(host_cat, host_mark)
        elif group_by == 'diameter':
            g = u'φ{:.0f}'.format(dia_mm) if dia_mm else u'—'
        else:
            g = shape or u'—'
        # Aggregate by: group + bar_mark + shape + dia + cut_length
        return (g, host_cat, host_mark, host_lv, bar_mark, shape, dia_mm, cut_mm)

    for rebar in (DB.FilteredElementCollector(doc)
                  .OfClass(_RebarClass)
                  .WhereElementIsNotElementType()
                  .ToElements()):
        try:
            # Phase filter
            if filter_ph_id is not None:
                try:
                    p = rebar.get_Parameter(DB.BuiltInParameter.PHASE_CREATED)
                    if p and p.HasValue and get_id_value(p.AsElementId()) == filter_ph_id:
                        continue
                except Exception:
                    pass

            # Host element
            host_el = None
            try:
                host_el = doc.GetElement(rebar.GetHostId())
            except Exception:
                pass

            # Host category filter
            if filter_host is not None:
                if host_el is None:
                    continue
                try:
                    if get_id_value(host_el.Category.Id) != filter_host:
                        continue
                except Exception:
                    continue

            # Level filter (via host)
            if filter_lv_id is not None:
                if host_el is None:
                    continue
                lv_match = False
                for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                            DB.BuiltInParameter.LEVEL_PARAM,
                            DB.BuiltInParameter.WALL_BASE_CONSTRAINT]:
                    try:
                        p = host_el.get_Parameter(bip)
                        if p and p.HasValue and get_id_value(p.AsElementId()) == filter_lv_id:
                            lv_match = True
                            break
                    except Exception:
                        pass
                if not lv_match:
                    continue

            info   = read_rebar(doc, rebar)
            h_cat  = _host_cat_label(host_el)
            h_mark = _host_mark(host_el)
            h_lv   = _host_level(host_el, doc)
            b_mark = info['mark'] or u'—'
            if info['partition']:
                b_mark = u'{} / {}'.format(info['partition'], b_mark)
            shape  = info['shape'] or u'—'
            dia_mm = float(info['diameter']) or None
            n      = info['quantity'] * info['members']
            cut_mm = float(info['bar_length_mm']) or None
            wpm    = _weight_per_m(dia_mm)
            total_m  = info['total_length_mm'] * info['members'] / 1000.0
            total_kg = info['mass_kg']

            k = _key(None, h_cat, h_mark, h_lv, b_mark, shape, dia_mm, cut_mm)
            if k not in rows_by_key:
                g = k[0]
                rows_by_key[k] = ScheduleRow(
                    group          = g,
                    host_cat       = h_cat,
                    host_mark      = h_mark,
                    host_level     = h_lv,
                    bar_mark       = b_mark,
                    shape          = shape,
                    dia_mm         = dia_mm,
                    n_bars         = 0,
                    cut_length_mm  = cut_mm,
                    total_length_m = 0.0,
                    wt_per_m       = wpm,
                    total_weight_kg= 0.0,
                    is_subtotal    = False,
                )
            rows_by_key[k].add(n, cut_mm, total_m, total_kg, get_id_value(rebar.Id))

        except Exception:
            log_swallowed(_LOG, u'collect_schedule.rebar')

    # Sort
    all_rows = sorted(rows_by_key.values(),
                      key=lambda r: (r.group or '', r.host_cat or '',
                                     r.host_mark or '', r.bar_mark or '',
                                     r.dia_mm or 0))

    # Build result with optional subtotals
    result = []
    current_group = None
    group_buf     = []

    def _flush(buf):
        if not buf:
            return
        sub = ScheduleRow(
            group          = buf[0].group,
            host_cat       = u'',
            host_mark      = u'SUBTOTAL',
            host_level     = u'',
            bar_mark       = u'',
            shape          = u'',
            dia_mm         = None,
            n_bars         = sum(r.n_bars or 0 for r in buf),
            cut_length_mm  = None,
            total_length_m = sum(r.total_length_m  or 0.0 for r in buf),
            wt_per_m       = None,
            total_weight_kg= sum(r.total_weight_kg or 0.0 for r in buf),
            is_subtotal    = True,
        )
        result.append(sub)

    for row in all_rows:
        g = row.group
        if g != current_group:
            if show_subtotals:
                _flush(group_buf)
            group_buf     = []
            current_group = g
        result.append(row)
        group_buf.append(row)
    if show_subtotals:
        _flush(group_buf)

    totals = ScheduleRow(
        group          = u'TOTAL',
        host_cat       = u'',
        host_mark      = u'GRAND TOTAL',
        host_level     = u'',
        bar_mark       = u'',
        shape          = u'',
        dia_mm         = None,
        n_bars         = sum(r.n_bars         or 0   for r in all_rows),
        cut_length_mm  = None,
        total_length_m = sum(r.total_length_m  or 0.0 for r in all_rows),
        wt_per_m       = None,
        total_weight_kg= sum(r.total_weight_kg or 0.0 for r in all_rows),
        is_subtotal    = True,
    )

    return result, totals


# ── export ────────────────────────────────────────────────────────────────────

_HEADERS = [u'Group', u'Host Cat.', u'Host Mark', u'Level', u'Bar Mark',
            u'Shape', u'Ø', u'No. Bars', u'Cut Length (mm)',
            u'Total Length (m)', u'Wt/m (kg/m)', u'Total Wt.']


# ── EC2 / EHE-08 compliance checks ───────────────────────────────────────────
#
# Checks performable from schedule data alone (no analysis results needed):
#   EC2-1-1:2004  §8.2   Minimum clear distance between bars
#   EC2-1-1:2004  §9.2.1 Minimum / maximum longitudinal reinforcement
#   EHE-08        §42.3  Minimum diameter per element type
#   General       §8.3   Maximum bar diameter (ductility / bond)
#
# All limits are applied per ScheduleRow (bar mark + host type combination).

_EC2_MIN_DIA = {
    u'Column':     12,   # EC2 §9.5.2(1)
    u'Beam':        8,   # EC2 §9.2.1(4)
    u'Foundation': 10,   # EC2 §9.8 / EHE §58
    u'Slab':        6,   # EC2 §9.3.1
    u'Wall':        6,   # EC2 §9.6.2
}
_EC2_MAX_DIA = 40   # practical maximum for standard structural use
_EC2_MIN_BARS_COLUMN = 4   # EC2 §9.5.2(1): min 4 bars in circular/rect column
_EC2_MAX_SPACING = 400     # mm, EC2 §9.3.1.1(3) slab main bars

_EHE_MIN_DIA = {
    u'Column':     12,
    u'Beam':       12,
    u'Foundation': 12,
    u'Slab':        6,
    u'Wall':        6,
}


class ComplianceIssue(object):
    """A single compliance finding for one ScheduleRow."""
    __slots__ = ['severity', 'code', 'message']
    def __init__(self, severity, code, message):
        self.severity = severity   # 'ERROR' | 'WARNING' | 'INFO'
        self.code     = code
        self.message  = message


def check_compliance(rows, standard='EC2'):
    """
    Run EC2 or EHE-08 compliance checks on a list of ScheduleRows.
    Returns dict: {row_index: [ComplianceIssue, ...]}
    standard: 'EC2' | 'EHE'
    """
    min_dia_map = _EHE_MIN_DIA if standard == 'EHE' else _EC2_MIN_DIA
    issues = {}

    for idx, row in enumerate(rows):
        if row.is_subtotal:
            continue
        row_issues = []
        dia = row.dia_mm
        hcat = row.host_cat or u''

        # ── Minimum diameter ──────────────────────────────────────────────────
        min_dia = min_dia_map.get(hcat)
        if dia is not None and min_dia is not None:
            if dia < min_dia:
                row_issues.append(ComplianceIssue(
                    'ERROR',
                    u'{} §min-dia'.format(standard),
                    u'Bar φ{:.0f}mm < minimum φ{}mm for {} ({})'.format(
                        dia, min_dia, hcat, standard)
                ))

        # ── Maximum diameter ──────────────────────────────────────────────────
        if dia is not None and dia > _EC2_MAX_DIA:
            row_issues.append(ComplianceIssue(
                'WARNING',
                u'EC2 §8.3',
                u'Bar φ{:.0f}mm > φ{}mm practical maximum — verify bond length'.format(
                    dia, _EC2_MAX_DIA)
            ))

        # ── Minimum bars in column ────────────────────────────────────────────
        if hcat == u'Column' and (row.n_bars or 0) < _EC2_MIN_BARS_COLUMN:
            row_issues.append(ComplianceIssue(
                'ERROR',
                u'EC2 §9.5.2',
                u'Column has only {} bar(s) — minimum is {}'.format(
                    row.n_bars or 0, _EC2_MIN_BARS_COLUMN)
            ))

        # ── Spacing check (if cut length available as proxy) ─────────────────
        # For slabs: if bar mark looks like a distributed layer, check spacing
        if hcat == u'Slab' and dia is not None and dia > 0 and row.cut_length_mm:
            spacing = row.cut_length_mm / max(row.n_bars or 1, 1)
            if spacing > _EC2_MAX_SPACING:
                row_issues.append(ComplianceIssue(
                    'WARNING',
                    u'EC2 §9.3.1.1',
                    u'Estimated bar spacing {:.0f}mm > {}mm max for slabs'.format(
                        spacing, _EC2_MAX_SPACING)
                ))

        if row_issues:
            issues[idx] = row_issues

    return issues


def compliance_summary(issues_dict):
    """Return a text summary of all compliance issues."""
    if not issues_dict:
        return u'✓  No compliance issues detected.'
    errors   = sum(1 for lst in issues_dict.values() for i in lst if i.severity == 'ERROR')
    warnings = sum(1 for lst in issues_dict.values() for i in lst if i.severity == 'WARNING')
    lines = [u'Compliance check: {} error(s), {} warning(s)\n'.format(errors, warnings)]
    for idx, issue_list in sorted(issues_dict.items()):
        for iss in issue_list:
            lines.append(u'[{}] {}  →  {}'.format(iss.severity, iss.code, iss.message))
    return u'\n'.join(lines)


def export_xlsx(rows, totals, path, project_name=''):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils  import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = u'Rebar Schedule'

    accent  = 'FF5F00'
    sub_bg  = 'FFD5B0'
    thin    = Side(border_style='thin', color='FFE0E0E0')
    bdr     = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fnt = Font(bold=True, color='FFFFFFFF', name='Century Gothic', size=10)
    sub_fnt = Font(bold=True, name='Century Gothic', size=10)
    tot_fnt = Font(bold=True, color='FFFFFFFF', name='Century Gothic', size=10)
    reg_fnt = Font(name='Century Gothic', size=9)
    center  = Alignment(horizontal='center', vertical='center')

    ws.merge_cells('A1:L1')
    ws['A1'] = u'REBAR SCHEDULE — {}'.format(project_name or 'PROJECT')
    ws['A1'].font      = Font(bold=True, size=14, name='Century Gothic', color=accent)
    ws['A1'].alignment = center

    for col, h in enumerate(_HEADERS, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font      = hdr_fnt
        cell.fill      = PatternFill('solid', fgColor=accent)
        cell.alignment = center
        cell.border    = bdr

    row_num = 4
    for r in rows:
        if r.is_subtotal:
            vals = [r.group_str, u'', r.host_mark_str, u'', u'', u'', u'',
                    r.n_bars or 0, u'',
                    round(r.total_length_m  or 0, 2),
                    u'',
                    r.total_wt_str]
            fill = PatternFill('solid', fgColor=sub_bg)
            font = sub_fnt
        else:
            vals = [r.group_str, r.host_cat_str, r.host_mark_str,
                    r.host_level_str, r.bar_mark_str, r.shape_str,
                    r.dia_str, r.n_bars or 0, r.cut_length_mm or u'',
                    round(r.total_length_m  or 0, 2) or u'',
                    round(r.wt_per_m        or 0, 3) or u'',
                    r.total_wt_str]
            fill = PatternFill('solid', fgColor='FFF0E8') if row_num % 2 == 0 else None
            font = reg_fnt

        for col, v in enumerate(vals, 1):
            cell = ws.cell(row=row_num, column=col, value=v)
            cell.font   = font
            cell.border = bdr
            if fill:
                cell.fill = fill
            if col >= 8:
                cell.alignment = center
        row_num += 1

    if totals:
        tot_vals = [u'', u'', u'GRAND TOTAL', u'', u'', u'', u'',
                    totals.n_bars or 0, u'',
                    round(totals.total_length_m  or 0, 2),
                    u'',
                    totals.total_wt_str]
        for col, v in enumerate(tot_vals, 1):
            cell = ws.cell(row=row_num, column=col, value=v)
            cell.font      = tot_fnt
            cell.fill      = PatternFill('solid', fgColor=accent)
            cell.border    = bdr
            cell.alignment = center

    widths = [28, 12, 14, 12, 12, 16, 8, 8, 16, 16, 12, 14]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.freeze_panes = 'A4'
    wb.save(path)


def export_csv(rows, totals, path):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(_HEADERS)
        for r in rows:
            w.writerow([
                r.group_str, r.host_cat_str, r.host_mark_str,
                r.host_level_str, r.bar_mark_str, r.shape_str,
                r.dia_str, r.n_bars or 0, r.cut_length_mm or '',
                round(r.total_length_m  or 0, 2),
                round(r.wt_per_m        or 0, 3),
                r.total_wt_str,
            ])
        if totals:
            w.writerow([u'', u'', u'GRAND TOTAL', u'', u'', u'', u'',
                        totals.n_bars or 0, u'',
                        round(totals.total_length_m  or 0, 2),
                        u'', totals.total_wt_str])
