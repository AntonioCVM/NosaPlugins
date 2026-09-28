# -*- coding: utf-8 -*-
"""Foundation Load Extractor — Logic

Extracts analytical model reactions at foundation support points and
aggregates them into per-foundation governing load envelopes.
"""
import math, io, csv
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.telemetry import log_swallowed
from nosa_utils import unit_conversion as _uc10
_LOG = u'ModelHealthHub/foundation_loads'
FT2M  = _uc10.FT_TO_M
FT2KN = FT2M * 4.44822   # ft·lbf → kN  (1 lbf = 4.44822 N)
FTLB2KNM = FT2KN * FT2M    # ft·lbf → kN·m



def _param_str(el, bip):
    try:
        p = el.get_Parameter(bip)
        if p and p.HasValue: return p.AsString() or ''
    except Exception: log_swallowed(_LOG, u'_param_str')
    return ''

def _level_name(doc, el):
    try:
        for bip in [DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                    DB.BuiltInParameter.LEVEL_PARAM,
                    DB.BuiltInParameter.WALL_BASE_CONSTRAINT]:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv: return lv.Name
    except Exception: log_swallowed(_LOG, u'_level_name')
    return '—'

def _xyz_str(pt):
    if pt is None: return '—'
    return '({:.3f}, {:.3f}, {:.3f})'.format(pt.X * FT2M, pt.Y * FT2M, pt.Z * FT2M)

def _collect_foundations(doc):
    return list(
        DB.FilteredElementCollector(doc)
          .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
          .WhereElementIsNotElementType()
          .ToElements()
    )

def _collect_walls_structural(doc):
    walls = []
    for el in (DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_Walls)
                 .WhereElementIsNotElementType()
                 .ToElements()):
        try:
            p = el.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT)
            if p and p.AsInteger(): walls.append(el)
        except Exception: log_swallowed(_LOG, u'_collect_walls_structural')
    return walls

def _get_analytical_reactions(doc, el):
    """
    Attempt to extract analytical node reactions from structural element.
    Returns list of {'node': XYZ, 'N': float, 'Mx': float, 'My': float,
                      'Vx': float, 'Vy': float} in SI units (kN / kN·m).
    """
    results = []
    try:
        # Try AnalyticalModel API (Revit 2022+)
        am = None
        try:
            am = DB.Structure.AnalyticalModelStick.GetAnalyticalModelStick(el)
        except Exception: pass  # nosa-lint: disable=NOSA006 - per-version API probe (AnalyticalModelStick vs GetAnalyticalModel)
        if am is None:
            try:
                am = el.GetAnalyticalModel()
            except Exception: pass  # nosa-lint: disable=NOSA006 - GetAnalyticalModel() was removed in Revit 2023+; fails by design on 2024-2027
        if am is None:
            return results

        # GetAnalyticalModelBoundaryConditions gives supports
        bcs = None
        try:
            bcs = list(am.GetAnalyticalModelBoundaryConditions())
        except Exception: log_swallowed(_LOG, u'_get_analytical_reactions')
        if not bcs:
            return results

        for bc in bcs:
            try:
                pt = None
                try:
                    pt = bc.Point
                except Exception: log_swallowed(_LOG, u'_get_analytical_reactions#2')
                # Reactions are not always available; provide zeros if missing
                N = Vx = Vy = Mx = My = 0.0
                try:
                    r = bc.GetReactions()
                    N  = r.Force.Z  * FT2KN
                    Vx = r.Force.X  * FT2KN
                    Vy = r.Force.Y  * FT2KN
                    Mx = r.Moment.X * FTLB2KNM
                    My = r.Moment.Y * FTLB2KNM
                except Exception: pass  # nosa-lint: disable=NOSA006 - reactions are often unavailable; zeros are the intended fallback
                results.append({'node': pt, 'N': N, 'Vx': Vx, 'Vy': Vy,
                                 'Mx': Mx, 'My': My})
            except Exception: log_swallowed(_LOG, u'_get_analytical_reactions#3')
    except Exception: log_swallowed(_LOG, u'_get_analytical_reactions#4')
    return results

def _envelope(reactions):
    """Return governing (max abs N, associated moments/shears)."""
    if not reactions:
        return {'N': None, 'Vx': None, 'Vy': None, 'Mx': None, 'My': None}
    governing = max(reactions, key=lambda r: abs(r.get('N', 0) or 0))
    return {k: governing.get(k) for k in ('N', 'Vx', 'Vy', 'Mx', 'My')}

def _fmt(v, decimals=1):
    if v is None: return '—'
    return round(v, decimals)

def get_foundation_loads(doc):
    """
    Returns list of dicts:
      id, mark, type_name, level, location, N_kN, Vx_kN, Vy_kN, Mx_kNm, My_kNm
    """
    rows = []
    elements = _collect_foundations(doc) + _collect_walls_structural(doc)

    for el in elements:
        try:
            eid    = get_id_value(el.Id)
            mark   = _param_str(el, DB.BuiltInParameter.ALL_MODEL_MARK) or '—'
            tname  = el.Name if hasattr(el, 'Name') else '—'
            level  = _level_name(doc, el)
            loc    = '—'
            try:
                lp = el.Location
                if isinstance(lp, DB.LocationPoint):
                    loc = '({:.2f}, {:.2f})'.format(lp.Point.X * FT2M,
                                                     lp.Point.Y * FT2M)
            except Exception: log_swallowed(_LOG, u'get_foundation_loads')

            reacts = _get_analytical_reactions(doc, el)
            env    = _envelope(reacts)

            rows.append({
                'id':     eid,
                'mark':   mark,
                'etype':   tname,
                'level':  level,
                'loc':    loc,
                'N_kN':   _fmt(env['N']),
                'Vx_kN':  _fmt(env['Vx']),
                'Vy_kN':  _fmt(env['Vy']),
                'Mx_kNm': _fmt(env['Mx']),
                'My_kNm': _fmt(env['My']),
                'nodes':  len(reacts),
            })
        except Exception: log_swallowed(_LOG, u'get_foundation_loads#2')

    rows.sort(key=lambda r: str(r['mark']))
    return rows

def export_pdf_report(rows, path, project_name=''):
    """
    Export a geotechnical foundation load report as HTML/PDF.
    Tries Chrome headless for PDF; falls back to HTML.
    Returns (out_path, is_pdf).
    """
    import io as _io, os, subprocess, datetime
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

    # Stats
    total = len(rows)
    with_data = sum(1 for r in rows if r.get('N_kN') and r.get('N_kN') != u'—')

    # Table rows HTML
    tbody = u''
    for r in rows:
        has = r.get('N_kN', u'—') != u'—'
        bg  = u'' if has else u" style='background:#FFF0E8;color:#999'"
        tbody += (
            u'<tr{bg}><td>{id}</td><td>{mark}</td><td>{typ}</td>'
            u'<td>{lvl}</td><td>{loc}</td>'
            u'<td>{N}</td><td>{Vx}</td><td>{Vy}</td>'
            u'<td>{Mx}</td><td>{My}</td><td>{nd}</td></tr>\n'
        ).format(
            bg=bg,
            id=r.get('id',''), mark=r.get('mark','—'),
            typ=r.get('etype','—'), lvl=r.get('level','—'), loc=r.get('loc','—'),
            N=r.get('N_kN','—'), Vx=r.get('Vx_kN','—'), Vy=r.get('Vy_kN','—'),
            Mx=r.get('Mx_kNm','—'), My=r.get('My_kNm','—'), nd=r.get('nodes','—')
        )

    html = u"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A3 landscape; margin: 15mm; }}
  body {{ font-family: 'Century Gothic', Arial, sans-serif; font-size: 9pt; color: #333; }}
  h1   {{ color: #FF5F00; font-size: 14pt; margin: 0 0 2px; }}
  .sub {{ color: #888; font-size: 9pt; margin: 0 0 14px; }}
  .stat {{ display: inline-block; margin: 0 20px 10px 0; font-weight: bold; color: #FF5F00; }}
  .stat span {{ font-weight: normal; color: #333; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 8pt; }}
  th {{ background: #FF5F00; color: white; padding: 5px 6px; text-align: left; }}
  td {{ padding: 3px 6px; border-bottom: 1px solid #E0E0E0; }}
  tr:nth-child(even) {{ background: #FAFAFA; }}
  .footer {{ margin-top: 12px; font-size: 7pt; color: #aaa; }}
  .note {{ background: #FFF3EC; border-left: 3px solid #FF5F00;
           padding: 6px 10px; margin-bottom: 12px; font-size: 8pt; }}
</style>
</head>
<body>
<h1>NOSA — Foundation Load Report</h1>
<p class="sub">{project} &nbsp;|&nbsp; Generated: {now}</p>
<div class="note">
  Loads extracted from Revit analytical model reactions.
  Values are envelope (max absolute) of all available load cases.
  Elements highlighted in orange have no analytical data.
</div>
<div class="stat">Total foundations: <span>{total}</span></div>
<div class="stat">With reactions: <span>{with_data}</span></div>
<div class="stat">No data: <span>{no_data}</span></div>
<table>
<thead>
  <tr><th>ID</th><th>Mark</th><th>Type</th><th>Level</th><th>Location (m)</th>
      <th>N (kN)</th><th>Vx (kN)</th><th>Vy (kN)</th>
      <th>Mx (kN·m)</th><th>My (kN·m)</th><th>Nodes</th></tr>
</thead>
<tbody>
{tbody}
</tbody>
</table>
<div class="footer">NOSA Engineering — Foundation Load Extractor</div>
</body></html>""".format(
        project=project_name, now=now,
        total=total, with_data=with_data, no_data=total - with_data,
        tbody=tbody
    )

    html_path = path.replace('.pdf', '.html') if path.lower().endswith('.pdf') else path + '.html'
    with _io.open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    chrome_candidates = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    ]
    for chrome in chrome_candidates:
        if os.path.exists(chrome):
            try:
                subprocess.Popen([
                    chrome, '--headless', '--disable-gpu',
                    '--print-to-pdf=' + path,
                    'file:///' + html_path.replace('\\', '/')
                ])
                return path, True
            except Exception:
                log_swallowed(_LOG, u'export_pdf_report')
    return html_path, False


def export_csv(rows, path):
    headers = ['ID', 'Mark', 'Type', 'Level', 'Location (m)',
               'N (kN)', 'Vx (kN)', 'Vy (kN)', 'Mx (kN·m)', 'My (kN·m)', 'Nodes']
    keys    = ['id', 'mark', 'etype', 'level', 'loc',
               'N_kN', 'Vx_kN', 'Vy_kN', 'Mx_kNm', 'My_kNm', 'nodes']
    with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow([r.get(k, '') for k in keys])


