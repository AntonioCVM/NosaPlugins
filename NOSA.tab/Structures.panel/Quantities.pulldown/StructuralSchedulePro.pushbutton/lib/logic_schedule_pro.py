import sys
# -*- coding: utf-8 -*-
"""Structural Schedule Pro — Logic"""
import io, csv, datetime, os

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
from nosa_utils.revit_helpers import get_id_value
from nosa_utils import unit_conversion as _uc10

FT2M = _uc10.FT_TO_M


def _category_map():
    """Lazy-build the category map inside Revit context."""
    from Autodesk.Revit.DB import BuiltInCategory
    return {
        'columns':     BuiltInCategory.OST_StructuralColumns,
        'beams':       BuiltInCategory.OST_StructuralFraming,
        'foundations': BuiltInCategory.OST_StructuralFoundation,
        'walls':       BuiltInCategory.OST_Walls,
        'floors':      BuiltInCategory.OST_Floors,
    }




def _param_str(el, bip):
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        p = el.get_Parameter(bip)
        if p and p.HasValue:
            return (p.AsString() or '').strip()
    except Exception:
        pass
    return ''


def _lookup_str(el, name):
    try:
        p = el.LookupParameter(name)
        if p and p.HasValue:
            return (p.AsString() or '').strip()
    except Exception:
        pass
    return ''


def _level_name(doc, el):
    from Autodesk.Revit.DB import BuiltInParameter, ElementId
    for bip in [BuiltInParameter.FAMILY_LEVEL_PARAM,
                BuiltInParameter.LEVEL_PARAM,
                BuiltInParameter.WALL_BASE_CONSTRAINT,
                BuiltInParameter.FLOOR_LEVEL_OFFSET_PARAM]:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                lv = doc.GetElement(p.AsElementId())
                if lv:
                    return lv.Name
        except Exception:
            pass
    return u'—'


def _length_m(el):
    from Autodesk.Revit.DB import BuiltInParameter, LocationCurve
    for bip in [BuiltInParameter.CURVE_ELEM_LENGTH,
                BuiltInParameter.INSTANCE_LENGTH_PARAM]:
        try:
            p = el.get_Parameter(bip)
            if p and p.HasValue:
                return round(p.AsDouble() * FT2M, 2)
        except Exception:
            pass
    try:
        lc = el.Location
        if isinstance(lc, LocationCurve):
            return round(lc.Curve.Length * FT2M, 2)
    except Exception:
        pass
    return None


def _material(el):
    try:
        from Autodesk.Revit.DB import BuiltInParameter, ElementId
        p = el.get_Parameter(BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if p and p.HasValue:
            eid = p.AsElementId()
            if eid != ElementId.InvalidElementId:
                mat = el.Document.GetElement(eid)
                if mat:
                    return mat.Name
    except Exception:
        pass
    return u'—'


def collect_schedule(doc, categories, extra_params=None):
    """
    Collect structural elements.
    Returns list of dicts: mark, type, level, length_m, material, category, id, ...
    """
    from Autodesk.Revit.DB import FilteredElementCollector, BuiltInParameter
    extra_params = extra_params or []
    cat_map = _category_map()
    rows = []
    seen_cats = set()

    for cat_key in categories:
        bic = cat_map.get(cat_key)
        if bic is None or bic in seen_cats:
            continue
        seen_cats.add(bic)
        try:
            elements = list(
                FilteredElementCollector(doc)
                  .OfCategory(bic)
                  .WhereElementIsNotElementType()
                  .ToElements()
            )
        except Exception:
            continue

        for el in elements:
            try:
                mark  = _param_str(el, BuiltInParameter.ALL_MODEL_MARK) or u'—'
                tname = getattr(el, 'Name', u'—') or u'—'
                level = _level_name(doc, el)
                len_m = _length_m(el)
                mat   = _material(el)
                cat_lbl = (el.Category.Name if el.Category else cat_key.title())

                row = {
                    'id':        get_id_value(el.Id),
                    'mark':      mark,
                    'etype':     tname,
                    'level':     level,
                    'length_m':  u'{:.2f}'.format(len_m) if len_m is not None else u'—',
                    'material':  mat,
                    'category':  cat_lbl,
                    'is_subtotal': False,
                }
                for pname in extra_params:
                    row['ep_' + pname] = _lookup_str(el, pname) or u'—'
                rows.append(row)
            except Exception:
                pass

    rows.sort(key=lambda r: (r['level'], r['category'], r['mark']))
    return rows


def subtotals(rows, group_by):
    if not rows or group_by not in ('level', 'category', 'material'):
        return rows
    result = []
    current_group = None
    group_count   = 0
    for row in rows:
        key = row.get(group_by, u'—')
        if key != current_group:
            if current_group is not None:
                result.append({
                    'mark': u'— {} —'.format(current_group),
                    'etype': u'Count: {}'.format(group_count),
                    'level': u'', 'length_m': u'', 'material': u'', 'category': u'',
                    'id': 0, 'is_subtotal': True,
                })
            current_group = key
            group_count   = 0
        result.append(row)
        group_count += 1
    if current_group is not None:
        result.append({
            'mark': u'— {} —'.format(current_group),
            'etype': u'Count: {}'.format(group_count),
            'level': u'', 'length_m': u'', 'material': u'', 'category': u'',
            'id': 0, 'is_subtotal': True,
        })
    return result


def export_pdf(rows, path, project_name='', extra_params=None):
    """
    Export schedule as HTML-to-PDF using the system print-to-PDF approach.
    Falls back to writing an HTML file and opening it when no PDF printer is available.
    The HTML file is styled for print (A4, Century Gothic, NOSA orange header).
    """
    extra_params = extra_params or []
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    cols = ['Mark', 'Type', 'Level', 'Length (m)', 'Material', 'Category']
    keys = ['mark', 'etype', 'level', 'length_m', 'material', 'category']
    for pname in extra_params:
        cols.append(pname)
        keys.append('ep_' + pname)

    # Build HTML table rows
    tbody = u''
    for row in rows:
        if row.get('is_subtotal'):
            cells = u''.join(
                u'<td colspan="{}"><strong>{}</strong></td>'.format(len(cols), row.get('mark', ''))
            )
            tbody += u'<tr class="subtotal">{}</tr>\n'.format(cells)
        else:
            cells = u''.join(u'<td>{}</td>'.format(row.get(k, '')) for k in keys)
            tbody += u'<tr>{}</tr>\n'.format(cells)

    thead = u''.join(u'<th>{}</th>'.format(c) for c in cols)

    total_elements = sum(1 for r in rows if not r.get('is_subtotal'))
    total_length   = sum(float(r.get('length_m') or 0) for r in rows if not r.get('is_subtotal'))

    html = u"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4 landscape; margin: 18mm; }}
  body {{ font-family: 'Century Gothic', Arial, sans-serif; font-size: 9pt; color: #333; }}
  h1   {{ color: #FF5F00; font-size: 14pt; margin: 0 0 4px; }}
  h2   {{ color: #666; font-size: 9pt; font-weight: normal; margin: 0 0 14px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th  {{ background: #FF5F00; color: white; padding: 5px 8px; text-align: left; font-size: 8pt; }}
  td  {{ padding: 4px 8px; border-bottom: 1px solid #E0E0E0; }}
  tr.subtotal td {{ background: #FFF3EC; font-weight: bold; }}
  tr:nth-child(even) {{ background: #FAFAFA; }}
  .footer {{ margin-top: 12px; font-size: 8pt; color: #999; }}
</style>
</head>
<body>
<h1>NOSA — Structural Schedule</h1>
<h2>{project} &nbsp;|&nbsp; Generated: {now} &nbsp;|&nbsp; {total} elements &nbsp;|&nbsp; Total length: {length:.2f} m</h2>
<table>
  <thead><tr>{thead}</tr></thead>
  <tbody>{tbody}</tbody>
</table>
<div class="footer">NOSA Engineering — Structural Schedule Pro</div>
</body></html>""".format(
        project=project_name, now=now,
        total=total_elements, length=total_length,
        thead=thead, tbody=tbody
    )

    # Write HTML to a temp file, then try to print to PDF
    import os, subprocess, tempfile
    html_path = path.replace('.pdf', '.html') if path.lower().endswith('.pdf') else path + '.html'
    with io.open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # Try printing to PDF via Chrome (silent) — gracefully falls back
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
                return path, True   # PDF generated
            except Exception:
                pass
    return html_path, False  # fell back to HTML


def export_csv(rows, path, project_name='', extra_params=None):
    extra_params = extra_params or []
    now  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    cols = ['Mark', 'Type', 'Level', 'Length (m)', 'Material', 'Category']
    keys = ['mark', 'etype', 'level', 'length_m', 'material', 'category']
    for pname in extra_params:
        cols.append(pname)
        keys.append('ep_' + pname)
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(u'\ufeff')  # one BOM: 'utf-8-sig' repeats it on every write in IronPython
        w = csv.writer(f)
        w.writerow(['NOSA STRUCTURAL SCHEDULE PRO'])
        w.writerow([project_name, '', '', '', '', now])
        w.writerow([])
        w.writerow(cols)
        for row in rows:
            w.writerow([row.get(k, '') for k in keys])
