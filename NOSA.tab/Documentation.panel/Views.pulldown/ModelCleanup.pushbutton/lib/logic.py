# -*- coding: utf-8 -*-
"""
ModelCleanup Logic — find orphan views, unused families/types/templates,
CAD imports, unplaced rooms, and trivial warnings.
"""
from pyrevit import DB
import math

def _get_id(eid):
    if hasattr(eid, 'Value'): return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))

# ── Orphan views ──────────────────────────────────────────────────────────────

def find_orphan_views(doc):
    """Views not placed on any sheet."""
    placed = set()
    for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements():
        for vpid in s.GetAllViewports():
            try:
                vp = doc.GetElement(vpid)
                placed.add(_get_id(vp.ViewId))
            except Exception:
                pass
    orphans = []
    skip_types = (DB.ViewType.Schedule, DB.ViewType.DrawingSheet, DB.ViewType.Legend,
                  DB.ViewType.ProjectBrowser, DB.ViewType.SystemBrowser, DB.ViewType.Undefined)
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate: continue
            if v.ViewType in skip_types: continue
            if _get_id(v.Id) not in placed:
                try:
                    vname = v.Name or str(v.Id)
                except Exception:
                    vname = str(v.Id)
                try:
                    vtype = str(v.ViewType).split('.')[-1]
                except Exception:
                    vtype = 'Unknown'
                orphans.append({'id': _get_id(v.Id), 'name': vname, 'type': vtype})
        except Exception:
            pass
    return sorted(orphans, key=lambda x: x['type'] + x['name'])

def purge_orphan_views(doc, view_ids):
    """Delete orphan views by ElementId integers. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, "ModelCleanup — Delete Orphan Views") as t:
        t.Start()
        for vid in view_ids:
            try:
                doc.Delete(DB.ICollection[DB.ElementId]([DB.ElementId(int(vid))]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed

# ── Unused family types ───────────────────────────────────────────────────────

def find_unused_families(doc):
    """Family symbols (types) with zero placed instances."""
    placed_type_ids = set()
    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements():
        try:
            tid = el.GetTypeId()
            if tid and tid != DB.ElementId.InvalidElementId:
                placed_type_ids.add(_get_id(tid))
        except Exception:
            pass
    unused = []
    for sym in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).ToElements():
        try:
            if _get_id(sym.Id) not in placed_type_ids:
                try:
                    fam_name = sym.Family.Name if (hasattr(sym, 'Family') and sym.Family is not None) else '—'
                except Exception:
                    fam_name = '—'
                try:
                    type_name = sym.Name or '—'
                except Exception:
                    type_name = '—'
                try:
                    cat_name = sym.Category.Name if sym.Category else '—'
                except Exception:
                    cat_name = '—'
                unused.append({'id': _get_id(sym.Id), 'family': fam_name,
                               'type': type_name, 'category': cat_name})
        except Exception:
            pass
    return sorted(unused, key=lambda x: x['category'] + x['family'])

def purge_unused_families(doc, symbol_ids):
    """Delete family symbol (type) elements. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, "ModelCleanup — Delete Unused Family Types") as t:
        t.Start()
        for sid in symbol_ids:
            try:
                doc.Delete(DB.ICollection[DB.ElementId]([DB.ElementId(int(sid))]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed

# ── Unused view templates ─────────────────────────────────────────────────────

def find_unused_view_templates(doc):
    """View templates assigned to no views."""
    used_tids = set()
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        if v.IsTemplate: continue
        try:
            tid = v.ViewTemplateId
            if tid != DB.ElementId.InvalidElementId:
                used_tids.add(_get_id(tid))
        except Exception:
            pass
    unused = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        if not v.IsTemplate: continue
        if _get_id(v.Id) not in used_tids:
            unused.append({'id': _get_id(v.Id), 'name': v.Name})
    return sorted(unused, key=lambda x: x['name'])

def purge_unused_templates(doc, template_ids):
    """Delete unused view templates. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, "ModelCleanup — Delete Unused Templates") as t:
        t.Start()
        for tid in template_ids:
            try:
                doc.Delete(DB.ICollection[DB.ElementId]([DB.ElementId(int(tid))]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed

# ── CAD / DWG imports ─────────────────────────────────────────────────────────

def find_cad_imports(doc):
    """
    Returns imported (not linked) CAD/DWG files in the model.
    Each entry: {'id', 'name', 'view', 'is_linked'}
    """
    results = []
    for el in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance).ToElements():
        try:
            is_linked = el.IsLinked
            try:
                cat_name = el.Category.Name if el.Category else '—'
            except Exception:
                cat_name = '—'
            try:
                view = doc.GetElement(el.OwnerViewId)
                view_name = view.Name if view else 'Model (3D)'
            except Exception:
                view_name = '—'
            results.append({
                'id':        _get_id(el.Id),
                'name':      cat_name,
                'view':      view_name,
                'is_linked': is_linked,
            })
        except Exception:
            pass
    return sorted(results, key=lambda x: (x['is_linked'], x['view'], x['name']))

def purge_cad_imports(doc, import_ids):
    """Delete CAD import instances. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, "ModelCleanup — Delete CAD Imports") as t:
        t.Start()
        for iid in import_ids:
            try:
                doc.Delete(DB.ICollection[DB.ElementId]([DB.ElementId(int(iid))]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed

# ── Unplaced rooms ────────────────────────────────────────────────────────────

def find_unplaced_rooms(doc):
    """Rooms with area == 0 (unplaced or unbounded)."""
    results = []
    for el in DB.FilteredElementCollector(doc)\
                .OfCategory(DB.BuiltInCategory.OST_Rooms)\
                .WhereElementIsNotElementType()\
                .ToElements():
        try:
            room = el
            area = room.Area
            if area < 0.001:
                try:
                    name = room.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or '—'
                except Exception:
                    name = '—'
                try:
                    number = room.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() or '—'
                except Exception:
                    number = '—'
                try:
                    level_p = room.get_Parameter(DB.BuiltInParameter.ROOM_LEVEL_ID)
                    if level_p:
                        lv = doc.GetElement(level_p.AsElementId())
                        level_name = lv.Name if lv else '—'
                    else:
                        level_name = '—'
                except Exception:
                    level_name = '—'
                results.append({'id': _get_id(room.Id), 'name': name,
                                'number': number, 'level': level_name})
        except Exception:
            pass
    return sorted(results, key=lambda x: (x['level'], x['number']))

def purge_unplaced_rooms(doc, room_ids):
    """Delete unplaced room elements. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, "ModelCleanup — Delete Unplaced Rooms") as t:
        t.Start()
        for rid in room_ids:
            try:
                doc.Delete(DB.ICollection[DB.ElementId]([DB.ElementId(int(rid))]))
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed

# ── Trivial warnings ──────────────────────────────────────────────────────────

_TRIVIAL_KEYWORDS = ['room', 'space', 'area', 'coordination', 'linked', 'import', 'detail']

def find_trivial_warnings(doc):
    """Warnings that are unlikely to affect structural integrity."""
    trivial = []
    try:
        for w in doc.GetWarnings():
            desc = (w.GetDescriptionText() or '').lower()
            if any(kw in desc for kw in _TRIVIAL_KEYWORDS):
                trivial.append({'description': w.GetDescriptionText()[:160],
                                'elements': len(list(w.GetFailingElements()))})
    except Exception:
        pass
    return trivial

# ── Main ──────────────────────────────────────────────────────────────────────

def run_all(doc):
    orphans   = find_orphan_views(doc)
    families  = find_unused_families(doc)
    templates = find_unused_view_templates(doc)
    warnings  = find_trivial_warnings(doc)
    cad       = find_cad_imports(doc)
    rooms     = find_unplaced_rooms(doc)
    return {
        'orphan_views':       orphans,
        'unused_families':    families,
        'unused_templates':   templates,
        'trivial_warnings':   warnings,
        'cad_imports':        cad,
        'unplaced_rooms':     rooms,
        'summary': {
            'orphan_views':    len(orphans),
            'unused_families': len(families),
            'unused_templates':len(templates),
            'trivial_warnings':len(warnings),
            'cad_imports':     len(cad),
            'unplaced_rooms':  len(rooms),
        }
    }
