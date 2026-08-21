# -*- coding: utf-8 -*-
"""
Revision Tracker v2.0 — Logic

Section 1: Revit Revision management (DB.Revision API)
Section 2: Sheet-Revision relationships
Section 3: Structural Snapshot Diff (preserved from v1.0)
"""
import io, os, json, datetime
from Autodesk.Revit import DB
from nosa_utils.revit_helpers import get_id_value
from pyrevit import revit
# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────



def get_all_revisions(doc):
    """Return DB.Revision elements sorted by sequence number."""
    col = (DB.FilteredElementCollector(doc)
           .OfClass(DB.Revision)
           .ToElements())
    return sorted(col, key=lambda r: r.SequenceNumber)


def create_revision(doc, description, date='', issued_by='', issued_to=''):
    """
    Create a new project revision.
    Returns the new DB.Revision element.
    """
    with revit.Transaction('NOSA — Create Revision'):
        rev = DB.Revision.Create(doc)
        rev.Description = description or u'New Revision'
        if date:
            rev.RevisionDate = date
        if issued_by:
            rev.IssuedBy = issued_by
        if issued_to:
            rev.IssuedTo = issued_to
    return rev


def set_issued(doc, rev_elem, issued):
    """Issue or unissue a revision."""
    label = u'NOSA — Issue Revision' if issued else u'NOSA — Unissue Revision'
    with revit.Transaction(label):
        rev_elem.Issued = issued


def delete_revision(doc, rev_elem):
    """
    Delete a revision.
    Raises if revision clouds reference it — Revit will refuse the deletion.
    """
    with revit.Transaction(u'NOSA — Delete Revision'):
        doc.Delete(rev_elem.Id)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Sheet-Revision relationships
# ─────────────────────────────────────────────────────────────────────────────

def get_sheets_with_status(doc, revision_id):
    """
    Return list of (ViewSheet, has_revision:bool) for every sheet in the project.
    has_revision=True if revision_id appears in sheet.GetAllRevisionIds()
    (includes both revision clouds and explicitly added revisions).
    Sorted by SheetNumber.
    """
    target_id_val = get_id_value(revision_id)
    results = []
    for sheet in (DB.FilteredElementCollector(doc)
                  .OfClass(DB.ViewSheet)
                  .ToElements()):
        try:
            rev_id_vals = set(get_id_value(rid) for rid in sheet.GetAllRevisionIds())
            has = target_id_val in rev_id_vals
        except Exception:
            has = False
        results.append((sheet, has))
    return sorted(results, key=lambda x: x[0].SheetNumber or '')


def add_revision_to_sheets(doc, revision_id, sheet_ids):
    """Add revision explicitly to a list of sheet ElementIds. Returns count."""
    count = 0
    with revit.Transaction(u'NOSA — Add Revision to Sheets'):
        for sid in sheet_ids:
            try:
                sheet = doc.GetElement(sid)
                if sheet:
                    sheet.AddRevision(revision_id)
                    count += 1
            except Exception:
                pass
    return count


def remove_revision_from_sheets(doc, revision_id, sheet_ids):
    """Remove revision from a list of sheet ElementIds. Returns count."""
    count = 0
    with revit.Transaction(u'NOSA — Remove Revision from Sheets'):
        for sid in sheet_ids:
            try:
                sheet = doc.GetElement(sid)
                if sheet:
                    sheet.RemoveRevision(revision_id)
                    count += 1
            except Exception:
                pass
    return count


def auto_assign_by_prefix(doc, revision_id, prefix):
    """
    Add revision to all sheets whose SheetNumber starts with `prefix`.
    Returns (assigned_count, skipped_already_had).
    """
    prefix_lo = prefix.strip().lower()
    target_id_val = get_id_value(revision_id)
    to_add = []
    already = 0

    for sheet in (DB.FilteredElementCollector(doc)
                  .OfClass(DB.ViewSheet)
                  .ToElements()):
        num = (sheet.SheetNumber or '').lower()
        if not num.startswith(prefix_lo):
            continue
        try:
            existing = set(get_id_value(rid) for rid in sheet.GetAllRevisionIds())
            if target_id_val in existing:
                already += 1
            else:
                to_add.append(sheet.Id)
        except Exception:
            to_add.append(sheet.Id)

    if to_add:
        add_revision_to_sheets(doc, revision_id, to_add)

    return len(to_add), already


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2b: Auto-assignment rules (prefix → revision description)
# Stored per-document in NOSA_Configs/revision_auto_rules.json
# ─────────────────────────────────────────────────────────────────────────────

_AUTO_RULES_DIR = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension',
    'NOSA_Configs'
)
_AUTO_RULES_FILE = os.path.join(_AUTO_RULES_DIR, 'revision_auto_rules.json')


def load_auto_rules(doc_title=''):
    """Return list of {prefix, revision_desc} dicts for the given document."""
    try:
        if os.path.exists(_AUTO_RULES_FILE):
            with open(_AUTO_RULES_FILE, 'r') as f:
                data = json.load(f)
            return data.get(doc_title, [])
    except Exception:
        pass
    return []


def save_auto_rules(rules, doc_title=''):
    """Persist auto-rules list for the given document."""
    try:
        os.makedirs(_AUTO_RULES_DIR, exist_ok=True)
        existing = {}
        if os.path.exists(_AUTO_RULES_FILE):
            with open(_AUTO_RULES_FILE, 'r') as f:
                existing = json.load(f)
        existing[doc_title] = rules
        with open(_AUTO_RULES_FILE, 'w') as f:
            json.dump(existing, f, indent=2)
        return True
    except Exception:
        return False


def apply_auto_rules(doc, rules):
    """
    Apply all rules in order.
    rules: list of {'prefix': str, 'revision_desc': str}

    For each rule, finds the first revision whose Description starts with
    revision_desc, then calls auto_assign_by_prefix.

    Returns list of {'prefix', 'revision_desc', 'assigned', 'skipped', 'error'}.
    """
    all_revs = get_all_revisions(doc)
    report   = []
    for rule in rules:
        prefix   = rule.get('prefix', '').strip()
        rev_desc = rule.get('revision_desc', '').strip()
        if not prefix or not rev_desc:
            continue
        # Find matching revision
        target_rev = None
        for rv in all_revs:
            try:
                if rv.Description.strip().lower().startswith(rev_desc.lower()):
                    target_rev = rv
                    break
            except Exception:
                pass
        if target_rev is None:
            report.append({'prefix': prefix, 'revision_desc': rev_desc,
                           'assigned': 0, 'skipped': 0,
                           'error': u'No revision matching "{}"'.format(rev_desc)})
            continue
        try:
            assigned, skipped = auto_assign_by_prefix(doc, target_rev.Id, prefix)
            report.append({'prefix': prefix, 'revision_desc': rev_desc,
                           'assigned': assigned, 'skipped': skipped, 'error': ''})
        except Exception as e:
            report.append({'prefix': prefix, 'revision_desc': rev_desc,
                           'assigned': 0, 'skipped': 0, 'error': str(e)})
    return report


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Structural Snapshot Diff  (preserved from v1.0)
# ─────────────────────────────────────────────────────────────────────────────

_SNAP_DIR = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension',
    'NOSA_Configs', 'Snapshots'
)

_TRACKED_BICS = None
_TRACK_PARAMS = None


def _tracked_bics():
    global _TRACKED_BICS
    if _TRACKED_BICS is None:
        _TRACKED_BICS = [
            ('Structural Columns',     DB.BuiltInCategory.OST_StructuralColumns),
            ('Structural Framing',     DB.BuiltInCategory.OST_StructuralFraming),
            ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
            ('Floors',                 DB.BuiltInCategory.OST_Floors),
            ('Walls',                  DB.BuiltInCategory.OST_Walls),
        ]
    return _TRACKED_BICS


def _track_params():
    global _TRACK_PARAMS
    if _TRACK_PARAMS is None:
        _TRACK_PARAMS = [
            DB.BuiltInParameter.ALL_MODEL_MARK,
            DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
            DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM,
            DB.BuiltInParameter.HOST_VOLUME_COMPUTED,
        ]
    return _TRACK_PARAMS


def _ensure_snap_dir():
    if not os.path.exists(_SNAP_DIR):
        os.makedirs(_SNAP_DIR)


def _collect_cat(doc, bic):
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(bic)
                .WhereElementIsNotElementType()
                .ToElements())


def _param_value(el, bip):
    try:
        p = el.get_Parameter(bip)
        if not p:
            return None
        if p.StorageType == DB.StorageType.String:
            return p.AsString()
        if p.StorageType == DB.StorageType.Integer:
            return p.AsInteger()
        if p.StorageType == DB.StorageType.Double:
            return round(p.AsDouble(), 4)
        if p.StorageType == DB.StorageType.ElementId:
            eid = p.AsElementId()
            if eid == DB.ElementId.InvalidElementId:
                return None
            el2 = p.Element.Document.GetElement(eid)
            return el2.Name if el2 and hasattr(el2, 'Name') else get_id_value(eid)
    except Exception:
        return None


def _element_snapshot(el, cat_name):
    params = {}
    for bip in _track_params():
        try:
            params[str(bip)] = _param_value(el, bip)
        except Exception:
            pass
    loc = None
    try:
        if isinstance(el.Location, DB.LocationPoint):
            pt = el.Location.Point
            loc = (round(pt.X, 3), round(pt.Y, 3), round(pt.Z, 3))
        elif isinstance(el.Location, DB.LocationCurve):
            p0 = el.Location.Curve.GetEndPoint(0)
            loc = (round(p0.X, 3), round(p0.Y, 3), round(p0.Z, 3))
    except Exception:
        pass
    return {
        'id':       get_id_value(el.Id),
        'name':     getattr(el, 'Name', ''),
        'category': cat_name,
        'type':     el.Name if hasattr(el, 'Name') else '',
        'location': loc,
        'params':   params,
    }


def take_snapshot(doc, label=None):
    _ensure_snap_dir()
    label = label or datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    elements = {}
    for cat_name, bic in _tracked_bics():
        for el in _collect_cat(doc, bic):
            snap = _element_snapshot(el, cat_name)
            elements[str(snap['id'])] = snap
    data = {
        'label':    label,
        'ts':       datetime.datetime.now().isoformat(),
        'count':    len(elements),
        'elements': elements,
    }
    fname = 'snapshot_{}.json'.format(
        datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    path = os.path.join(_SNAP_DIR, fname)
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    return path, label, len(elements)


def list_snapshots():
    _ensure_snap_dir()
    snaps = []
    for fn in sorted(os.listdir(_SNAP_DIR)):
        if not fn.endswith('.json'):
            continue
        try:
            with io.open(os.path.join(_SNAP_DIR, fn), encoding='utf-8') as f:
                d = json.load(f)
            snaps.append({
                'file':  fn,
                'label': d.get('label', fn),
                'ts':    d.get('ts', ''),
                'count': d.get('count', 0),
            })
        except Exception:
            pass
    return snaps


def load_snapshot(fname):
    path = os.path.join(_SNAP_DIR, fname)
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


def delete_snapshot(fname):
    path = os.path.join(_SNAP_DIR, fname)
    if os.path.exists(path):
        os.remove(path)


def compare(doc, snapshot_data):
    current = {}
    for cat_name, bic in _tracked_bics():
        for el in _collect_cat(doc, bic):
            snap = _element_snapshot(el, cat_name)
            current[str(snap['id'])] = snap

    saved = snapshot_data.get('elements', {})
    added, removed, changed = [], [], []

    for eid, cur in current.items():
        if eid not in saved:
            added.append(cur)
        else:
            old = saved[eid]
            diffs = [k for k in cur.get('params', {})
                     if cur['params'].get(k) != old.get('params', {}).get(k)]
            loc_changed = cur.get('location') != old.get('location')
            if diffs or loc_changed:
                changed.append({
                    'current':          cur,
                    'previous':         old,
                    'diff_params':      diffs,
                    'location_changed': loc_changed,
                })

    for eid, old in saved.items():
        if eid not in current:
            removed.append(old)

    return {
        'added':   added,
        'removed': removed,
        'changed': changed,
        'summary': {
            'added':   len(added),
            'removed': len(removed),
            'changed': len(changed),
        },
    }
