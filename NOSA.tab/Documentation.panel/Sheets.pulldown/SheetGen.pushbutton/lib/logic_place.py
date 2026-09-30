# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils.collectors import collect_views, placed_view_ids
from nosa_utils import unit_conversion as _uc10

_MM_TO_FT = _uc10.MM_TO_FT


def _placeable_types():
    names = ['FloorPlan', 'CeilingPlan', 'EngineeringPlan', 'AreaPlan',
             'Elevation', 'Section', 'Detail', 'ThreeD', 'DraftingView',
             'Rendering']
    result = set()
    for n in names:
        try:
            result.add(getattr(DB.ViewType, n))
        except AttributeError:
            pass
    return result


def unplaced_views(doc):
    """Placeable model/drafting views not on any sheet."""
    placed = placed_view_ids(doc, all_placed=True)
    result = []
    for v in collect_views(doc, include_types=_placeable_types()):
        try:
            if get_id_value(v.Id) in placed:
                continue
            result.append({'view': v, 'name': v.Name or u'',
                           'type': str(v.ViewType).split('.')[-1]})
        except Exception:
            pass
    result.sort(key=lambda r: (r['type'], r['name'].lower()))
    return result


def legend_views(doc):
    result = []
    try:
        legend_t = DB.ViewType.Legend
    except AttributeError:
        return result
    for v in collect_views(doc, include_types=(legend_t,)):
        try:
            result.append({'view': v, 'name': v.Name or u''})
        except Exception:
            pass
    result.sort(key=lambda r: r['name'].lower())
    return result


def real_sheets(doc):
    result = []
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            if getattr(s, 'IsPlaceholder', False):
                continue
            result.append({'sheet': s,
                           'label': u'{} — {}'.format(s.SheetNumber, s.Name)})
        except Exception:
            pass
    result.sort(key=lambda r: r['label'].lower())
    return result


def placeholder_sheets(doc):
    result = []
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            if getattr(s, 'IsPlaceholder', False):
                result.append({'sheet': s, 'number': s.SheetNumber or u'',
                               'name': s.Name or u''})
        except Exception:
            pass
    result.sort(key=lambda r: r['number'])
    return result


def _sheet_rect(sheet):
    """Usable sheet rectangle (min_u, min_v, max_u, max_v) from Outline."""
    o = sheet.Outline
    return o.Min.U, o.Min.V, o.Max.U, o.Max.V


def _fmt_number(prefix, n, pad):
    return u'{}{}'.format(prefix, u'{}'.format(n).zfill(max(0, int(pad))))


def _taken_numbers(doc):
    taken = set()
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        try:
            taken.add((s.SheetNumber or u'').lower())
        except Exception:
            pass
    return taken


def create_sheets_with_views(doc, views, tb_id, prefix, start, pad,
                             name_from_view=True, fixed_name=u''):
    """One new sheet per view; viewport centred. Returns (created, failed, errors)."""
    created = failed = 0
    errors = []
    taken = _taken_numbers(doc)
    n = int(start)

    with DB.Transaction(doc, u'NOSA — Sheets from Views') as t:
        t.Start()
        for rec in views:
            view = rec['view']
            try:
                num = _fmt_number(prefix, n, pad)
                while num.lower() in taken:
                    n += 1
                    num = _fmt_number(prefix, n, pad)
                sheet = DB.ViewSheet.Create(doc, tb_id)
                sheet.SheetNumber = num
                taken.add(num.lower())
                try:
                    sheet.Name = view.Name if name_from_view else (fixed_name or view.Name)
                except Exception:
                    pass
                if DB.Viewport.CanAddViewToSheet(doc, sheet.Id, view.Id):
                    u0, v0, u1, v1 = _sheet_rect(sheet)
                    centre = DB.XYZ((u0 + u1) / 2.0, (v0 + v1) / 2.0, 0)
                    DB.Viewport.Create(doc, sheet.Id, view.Id, centre)
                created += 1
                n += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}: {}'.format(rec['name'], ex))
        t.Commit()
    return created, failed, errors


def place_views_grid(doc, sheet, views, cols, margin_mm=20.0):
    """Place views on one sheet in a grid of `cols` columns. Returns (placed, skipped, errors)."""
    placed = skipped = 0
    errors = []
    cols = max(1, int(cols))
    rows = (len(views) + cols - 1) // cols
    margin = margin_mm * _MM_TO_FT

    u0, v0, u1, v1 = _sheet_rect(sheet)
    u0 += margin; v0 += margin; u1 -= margin; v1 -= margin
    cell_w = (u1 - u0) / cols
    cell_h = (v1 - v0) / max(1, rows)

    with DB.Transaction(doc, u'NOSA — Place Views on Sheet') as t:
        t.Start()
        for i, rec in enumerate(views):
            view = rec['view']
            try:
                if not DB.Viewport.CanAddViewToSheet(doc, sheet.Id, view.Id):
                    skipped += 1
                    errors.append(u'"{}" cannot be placed on this sheet.'.format(rec['name']))
                    continue
                col = i % cols
                row = i // cols
                cx = u0 + cell_w * (col + 0.5)
                cy = v1 - cell_h * (row + 0.5)   # fill top-down
                DB.Viewport.Create(doc, sheet.Id, view.Id, DB.XYZ(cx, cy, 0))
                placed += 1
            except Exception as ex:
                skipped += 1
                errors.append(u'{}: {}'.format(rec['name'], ex))
        t.Commit()
    return placed, skipped, errors


def place_legend_on_sheets(doc, legend_view, sheets, u_mm, v_mm):
    """Place the same legend on many sheets at (u,v) mm from bottom-left. Returns (placed, skipped, errors)."""
    placed = skipped = 0
    errors = []
    du = u_mm * _MM_TO_FT
    dv = v_mm * _MM_TO_FT

    with DB.Transaction(doc, u'NOSA — Place Legend on Sheets') as t:
        t.Start()
        for rec in sheets:
            sheet = rec['sheet']
            try:
                if not DB.Viewport.CanAddViewToSheet(doc, sheet.Id, legend_view.Id):
                    skipped += 1
                    continue
                u0, v0, _, _ = _sheet_rect(sheet)
                DB.Viewport.Create(doc, sheet.Id, legend_view.Id,
                                   DB.XYZ(u0 + du, v0 + dv, 0))
                placed += 1
            except Exception as ex:
                skipped += 1
                errors.append(u'{}: {}'.format(rec['label'], ex))
        t.Commit()
    return placed, skipped, errors


def create_placeholders(doc, prefix, start, count, pad, name):
    """Create placeholder sheets in bulk. Returns (created, failed, errors)."""
    created = failed = 0
    errors = []
    taken = _taken_numbers(doc)
    n = int(start)

    with DB.Transaction(doc, u'NOSA — Create Placeholder Sheets') as t:
        t.Start()
        for _ in range(int(count)):
            try:
                num = _fmt_number(prefix, n, pad)
                while num.lower() in taken:
                    n += 1
                    num = _fmt_number(prefix, n, pad)
                ph = DB.ViewSheet.CreatePlaceholder(doc)
                ph.SheetNumber = num
                taken.add(num.lower())
                try:
                    ph.Name = name or u'PLACEHOLDER'
                except Exception:
                    pass
                created += 1
                n += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}'.format(ex))
        t.Commit()
    return created, failed, errors


def convert_placeholders(doc, placeholders, tb_id):
    """
    Convert placeholders to real sheets: cache number/name, delete the
    placeholder, create a real sheet with the title block, restore data.
    Returns (converted, failed, errors).
    """
    converted = failed = 0
    errors = []

    with DB.Transaction(doc, u'NOSA — Convert Placeholder Sheets') as t:
        t.Start()
        for rec in placeholders:
            ph = rec['sheet']
            try:
                num, name = rec['number'], rec['name']
                doc.Delete(ph.Id)
                sheet = DB.ViewSheet.Create(doc, tb_id)
                sheet.SheetNumber = num
                try:
                    sheet.Name = name
                except Exception:
                    pass
                converted += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}: {}'.format(rec['number'], ex))
        t.Commit()
    return converted, failed, errors
