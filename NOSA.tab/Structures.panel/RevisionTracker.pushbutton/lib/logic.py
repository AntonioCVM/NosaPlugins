# -*- coding: utf-8 -*-
"""
RevisionTracker Logic — snapshot-based delta detection.
Saves a JSON snapshot of structural elements + parameters.
Compares current model against snapshot to find Added / Removed / Changed.
"""
import os, json, datetime
from pyrevit import DB

_SNAP_DIR = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs', 'Snapshots'
)
_TRACKED_BICS = [
    ('Structural Columns',    DB.BuiltInCategory.OST_StructuralColumns),
    ('Structural Framing',    DB.BuiltInCategory.OST_StructuralFraming),
    ('Structural Foundations',DB.BuiltInCategory.OST_StructuralFoundation),
    ('Floors',                DB.BuiltInCategory.OST_Floors),
    ('Walls',                 DB.BuiltInCategory.OST_Walls),
]
_TRACK_PARAMS = [
    DB.BuiltInParameter.ALL_MODEL_MARK,
    DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
    DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM,
    DB.BuiltInParameter.HOST_VOLUME_COMPUTED,
]


def _ensure_dir():
    if not os.path.exists(_SNAP_DIR): os.makedirs(_SNAP_DIR)

def _get_id(eid):
    if hasattr(eid, 'Value'): return eid.Value
    if hasattr(eid, 'IntegerValue'): return eid.IntegerValue
    return int(str(eid))

def _collect(doc, bic):
    return list(DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements())

def _param_value(el, bip):
    try:
        p = el.get_Parameter(bip)
        if not p: return None
        if p.StorageType == DB.StorageType.String:  return p.AsString()
        if p.StorageType == DB.StorageType.Integer: return p.AsInteger()
        if p.StorageType == DB.StorageType.Double:  return round(p.AsDouble(), 4)
        if p.StorageType == DB.StorageType.ElementId:
            eid = p.AsElementId()
            if eid == DB.ElementId.InvalidElementId: return None
            el2 = p.Element.Document.GetElement(eid)
            return el2.Name if el2 and hasattr(el2, 'Name') else _get_id(eid)
    except Exception:
        return None

def _element_snapshot(el, cat_name):
    params = {}
    for bip in _TRACK_PARAMS:
        try: params[str(bip)] = _param_value(el, bip)
        except Exception: pass
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
    return {'id': _get_id(el.Id), 'name': getattr(el, 'Name', ''), 'category': cat_name,
            'type': el.Name if hasattr(el, 'Name') else '', 'location': loc, 'params': params}


def take_snapshot(doc, label=None):
    _ensure_dir()
    label = label or datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    elements = {}
    for cat_name, bic in _TRACKED_BICS:
        for el in _collect(doc, bic):
            snap = _element_snapshot(el, cat_name)
            elements[str(snap['id'])] = snap
    data = {'label': label, 'ts': datetime.datetime.now().isoformat(),
            'count': len(elements), 'elements': elements}
    fname = 'snapshot_{}.json'.format(datetime.datetime.now().strftime('%Y%m%d_%H%M%S'))
    path = os.path.join(_SNAP_DIR, fname)
    with open(path, 'w') as f: json.dump(data, f, indent=2)
    return path, label, len(elements)

def list_snapshots():
    _ensure_dir()
    snaps = []
    for fn in sorted(os.listdir(_SNAP_DIR)):
        if not fn.endswith('.json'): continue
        try:
            with open(os.path.join(_SNAP_DIR, fn)) as f:
                d = json.load(f)
            snaps.append({'file': fn, 'label': d.get('label', fn), 'ts': d.get('ts', ''),
                          'count': d.get('count', 0)})
        except Exception:
            pass
    return snaps

def load_snapshot(fname):
    path = os.path.join(_SNAP_DIR, fname)
    with open(path) as f: return json.load(f)

def delete_snapshot(fname):
    path = os.path.join(_SNAP_DIR, fname)
    if os.path.exists(path): os.remove(path)

def compare(doc, snapshot_data):
    current = {}
    for cat_name, bic in _TRACKED_BICS:
        for el in _collect(doc, bic):
            snap = _element_snapshot(el, cat_name)
            current[str(snap['id'])] = snap
    saved = snapshot_data.get('elements', {})
    added, removed, changed = [], [], []
    for eid, cur in current.items():
        if eid not in saved:
            added.append(cur)
        else:
            old = saved[eid]
            diffs = [k for k in cur.get('params', {}) if cur['params'].get(k) != old.get('params', {}).get(k)]
            loc_changed = cur.get('location') != old.get('location')
            if diffs or loc_changed:
                changed.append({'current': cur, 'previous': old, 'diff_params': diffs, 'location_changed': loc_changed})
    for eid, old in saved.items():
        if eid not in current:
            removed.append(old)
    return {'added': added, 'removed': removed, 'changed': changed,
            'summary': {'added': len(added), 'removed': len(removed), 'changed': len(changed)}}
