# -*- coding: utf-8 -*-
import datetime
import io
import json
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value

_MM_PER_FOOT = 304.8
_SNAP_DIR = os.path.join(
    os.getenv('APPDATA', ''), 'pyRevit', 'Extensions', 'NOSA.extension',
    'NOSA_Configs', 'LinkSnapshots'
)

_TRACK_CATS = None


def _track_categories():
    global _TRACK_CATS
    if _TRACK_CATS is None:
        _TRACK_CATS = [
            ('Structural Columns', DB.BuiltInCategory.OST_StructuralColumns),
            ('Structural Framing', DB.BuiltInCategory.OST_StructuralFraming),
            ('Structural Foundations', DB.BuiltInCategory.OST_StructuralFoundation),
            ('Floors', DB.BuiltInCategory.OST_Floors),
            ('Walls', DB.BuiltInCategory.OST_Walls),
            ('Grids', DB.BuiltInCategory.OST_Grids),
        ]
    return _TRACK_CATS


def _ft_to_mm(ft):
    return round(ft * _MM_PER_FOOT, 2)


def get_links(doc):
    links = []
    for link in (DB.FilteredElementCollector(doc)
                 .OfClass(DB.RevitLinkInstance)
                 .ToElements()):
        try:
            link_doc = link.GetLinkDocument()
            if link_doc:
                links.append((link, link_doc))
        except Exception:
            pass
    return links


def _collect_levels(link_doc):
    data = {}
    for lvl in DB.FilteredElementCollector(link_doc).OfClass(DB.Level).ToElements():
        try:
            data[lvl.Name.strip()] = _ft_to_mm(lvl.Elevation)
        except Exception:
            pass
    return data


def _collect_grids(link_doc):
    data = {}
    for g in DB.FilteredElementCollector(link_doc).OfClass(DB.Grid).ToElements():
        try:
            mid = g.Curve.Evaluate(0.5, True)
            data[g.Name.strip()] = (_ft_to_mm(mid.X), _ft_to_mm(mid.Y))
        except Exception:
            pass
    return data


def _count_elements(link_doc):
    counts = {}
    for label, cat in _track_categories():
        try:
            n = (DB.FilteredElementCollector(link_doc)
                 .OfCategory(cat)
                 .WhereElementIsNotElementType()
                 .ToElements())
            counts[label] = len(list(n))
        except Exception:
            counts[label] = 0
    return counts


def _snapshot_payload(link, link_doc):
    return {
        'link_id': get_id_value(link.Id),
        'link_name': link.Name,
        'doc_title': link_doc.Title,
        'ts': datetime.datetime.now().isoformat(),
        'levels': _collect_levels(link_doc),
        'grids': _collect_grids(link_doc),
        'counts': _count_elements(link_doc),
    }


def _ensure_dir():
    if not os.path.exists(_SNAP_DIR):
        os.makedirs(_SNAP_DIR)


def _snap_path(link_id_val):
    return os.path.join(_SNAP_DIR, 'link_{}.json'.format(link_id_val))


def take_snapshot(doc, link):
    link_doc = link.GetLinkDocument()
    if link_doc is None:
        raise ValueError(u'Link is not loaded.')
    _ensure_dir()
    payload = _snapshot_payload(link, link_doc)
    path = _snap_path(payload['link_id'])
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    return path, payload


def list_snapshots():
    _ensure_dir()
    snaps = []
    for fn in sorted(os.listdir(_SNAP_DIR)):
        if not fn.endswith('.json'):
            continue
        try:
            with io.open(os.path.join(_SNAP_DIR, fn), encoding='utf-8') as f:
                d = json.load(f)
            snaps.append({
                'file': fn,
                'link_name': d.get('link_name', fn),
                'doc_title': d.get('doc_title', u''),
                'ts': d.get('ts', u''),
            })
        except Exception:
            pass
    return snaps


def load_snapshot_for_link(link_id_val):
    path = _snap_path(link_id_val)
    if not os.path.exists(path):
        return None
    with io.open(path, encoding='utf-8') as f:
        return json.load(f)


class ChangeItem(object):
    def __init__(self, category, detail, severity):
        self.category = category
        self.detail = detail
        self.severity = severity


def compare_link(doc, link):
    link_doc = link.GetLinkDocument()
    if link_doc is None:
        return [ChangeItem(u'Link', u'Linked model is not loaded.', 'red')]

    saved = load_snapshot_for_link(get_id_value(link.Id))
    if saved is None:
        return [ChangeItem(u'Snapshot', u'No baseline snapshot — take one first.', 'amber')]

    current = _snapshot_payload(link, link_doc)
    changes = []

    for name, elev in current['levels'].items():
        old = saved.get('levels', {}).get(name)
        if old is None:
            changes.append(ChangeItem(u'Levels', u'Added level "{}" at {} mm'.format(name, elev), 'amber'))
        elif abs(old - elev) > 1.0:
            changes.append(ChangeItem(
                u'Levels', u'Level "{}" moved {:.1f} mm (was {:.1f})'.format(name, elev - old, old), 'red'))

    for name in saved.get('levels', {}):
        if name not in current['levels']:
            changes.append(ChangeItem(u'Levels', u'Removed level "{}"'.format(name), 'red'))

    for name, pos in current['grids'].items():
        old = saved.get('grids', {}).get(name)
        if old is None:
            changes.append(ChangeItem(u'Grids', u'Added grid "{}"'.format(name), 'amber'))
        else:
            dx = pos[0] - old[0]
            dy = pos[1] - old[1]
            if abs(dx) > 5 or abs(dy) > 5:
                changes.append(ChangeItem(
                    u'Grids', u'Grid "{}" moved ({:.0f}, {:.0f}) mm'.format(name, dx, dy), 'red'))

    for name in saved.get('grids', {}):
        if name not in current['grids']:
            changes.append(ChangeItem(u'Grids', u'Removed grid "{}"'.format(name), 'red'))

    for label, count in current['counts'].items():
        old = saved.get('counts', {}).get(label, 0)
        if count != old:
            changes.append(ChangeItem(
                u'Geometry', u'{} count: {} → {}'.format(label, old, count),
                'red' if abs(count - old) > 5 else 'amber'))

    if not changes:
        changes.append(ChangeItem(u'Summary', u'No changes detected since last snapshot.', 'green'))
    return changes
