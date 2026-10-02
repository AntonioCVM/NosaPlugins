# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — partitions (T7.1): name the BBS member of every reinforced host and
count identical hosts once, as 'No. of mbrs' = N on one representative (user decision
2026-10-02). The other identical hosts keep their bars in 3D, flagged
NOSA_Rebar_Show_In_Schedule = No so the template's BBS filter leaves them out.
"""
from __future__ import absolute_import, print_function, unicode_literals
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)
_lib = os.path.abspath(os.path.join(_here, '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_FT_TO_MM = 304.8
_LENGTH_TOLERANCE_MM = 5.0
_ROW_BAND_MM = 500.0

# Revit category name (BuiltInCategory) -> BBS member prefix
PREFIXES = tuple(zip((u'OST_StructuralColumns', u'OST_StructuralFraming', u'OST_StructuralFoundation',
                      u'OST_Floors', u'OST_Walls'), u'CBFSW'))
_DEFAULT_PREFIX = u'M'


def prefix_for(category):
    for name, prefix in PREFIXES:
        if category == name:
            return prefix
    return _DEFAULT_PREFIX


def bar_signature(layer, shape_code, shape_params, diameter_mm, quantity, unit_length_mm):
    """One Rebar element as compared between hosts: position in the host is ignored."""
    step = _LENGTH_TOLERANCE_MM
    return (layer or u'', shape_code or u'', shape_params or u'', int(round(diameter_mm or 0)),
            int(quantity or 1), int(round((unit_length_mm or 0.0) / step)))


def fingerprint(category, host_type, signatures):
    """Hosts are identical when category, type and the sorted bar signatures all match."""
    return (category or u'', host_type or u'', tuple(sorted(signatures)))


def _sort_key(host):
    # level first, then plan rows from the top of the drawing, then left to right
    return (round(host.get('elevation_mm') or 0.0),
            -int((host.get('y_mm') or 0.0) // _ROW_BAND_MM),
            host.get('x_mm') or 0.0,
            host['id'])


def _joined_marks(marks):
    if len(marks) <= 3:
        return u', '.join(marks)
    return u'{} to {}'.format(marks[0], marks[-1])


def plan(hosts, group_identical=True):
    """
    hosts: dicts with id, category, mark, elevation_mm, x_mm, y_mm, fingerprint.
    Returns {host id: {'partition', 'group', 'representative', 'members'}}: the host Mark
    names the partition when there is one, otherwise prefix + sequence by level and position.
    Identical hosts share one partition; the first in drawing order represents them all.
    """
    groups = {}
    order = []
    for host in sorted(hosts, key=_sort_key):
        key = (host['category'], host['fingerprint']) if group_identical else ('single', host['id'])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(host)

    used = set(h['mark'] for h in hosts if h.get('mark'))
    counters = {}
    result = {}
    for index, key in enumerate(order, start=1):
        members = groups[key]
        marks = sorted(set(h['mark'] for h in members if h.get('mark')), key=_natural)
        if marks:
            name = _joined_marks(marks)
        else:
            prefix = prefix_for(members[0]['category'])
            while True:
                counters[prefix] = counters.get(prefix, 0) + 1
                name = u'{}{}'.format(prefix, counters[prefix])
                if name not in used:
                    break
        used.add(name)
        for position, host in enumerate(members):
            result[host['id']] = {
                'partition': name,
                'group': index,
                'representative': position == 0,
                'members': len(members) if position == 0 else 1,
            }
    return result


def _natural(text):
    digits = u''.join(c for c in text if c.isdigit())
    return (u''.join(c for c in text if not c.isdigit()), int(digits) if digits else 0, text)


# ---------------------------------------------------------------- Revit side


def _category_name(element):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    try:
        value = get_id_value(element.Category.Id)
        for name, _prefix in PREFIXES:
            if value == int(getattr(DB.BuiltInCategory, name)):
                return name
    except Exception:
        log_swallowed(_LOG, u'_category_name')
    return u''


def _host_mark(host):
    from Autodesk.Revit import DB  # Lazy import
    try:
        return (host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString() or u'').strip()
    except Exception:
        return u''


def _level(doc, host):
    """(level name, elevation mm) — the host's own level, or its bounding box base."""
    from Autodesk.Revit import DB  # Lazy import
    level = None
    for getter in (lambda: host.LevelId,
                   lambda: host.get_Parameter(DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM).AsElementId(),
                   lambda: host.get_Parameter(DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId()):
        try:
            level = doc.GetElement(getter())
        except Exception:
            level = None
        if isinstance(level, DB.Level):
            return level.Name, level.Elevation * _FT_TO_MM
    box = host.get_BoundingBox(None)
    return u'', (box.Min.Z * _FT_TO_MM if box else 0.0)


def _type_name(doc, host):
    from nosa_utils.revit_helpers import element_name
    try:
        return element_name(doc.GetElement(host.GetTypeId())) or u''
    except Exception:
        return u''


def _signature(doc, rebar):
    from nosa_utils import shared_params
    import rebar_bending
    try:
        bar_type = doc.GetElement(rebar.GetTypeId())
        diameter = bar_type.BarNominalDiameter * _FT_TO_MM
    except Exception:
        diameter = 0.0
    try:
        quantity = rebar.Quantity
    except Exception:
        quantity = 1
    return bar_signature(shared_params.read(rebar, u'NOSA_Rebar_Layer', u''),
                         shared_params.read(rebar, u'NOSA_Rebar_Shape_Code', u''),
                         shared_params.read(rebar, u'NOSA_Rebar_Shape_Params', u''),
                         diameter, quantity, rebar_bending.unit_cut_length_mm(rebar))


def is_finalized(rebar):
    from nosa_utils import shared_params
    return shared_params.read(rebar, u'NOSA_Rebar_Finalized') in (1, u'1')


def collect_hosts(doc):
    """Hosts carrying NOSA bars (any batch), with what plan() and the dialog need."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import shared_params
    from nosa_utils.revit_helpers import get_id_value
    bars_by_host = {}
    collector = DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_Rebar).WhereElementIsNotElementType()
    for rebar in collector:
        if not shared_params.read(rebar, u'NOSA_Rebar_Batch_Id'):
            continue
        try:
            host_id = rebar.GetHostId()
        except Exception:
            continue
        bars_by_host.setdefault(get_id_value(host_id), (host_id, []))[1].append(rebar)

    hosts = []
    for value, (host_id, rebars) in bars_by_host.items():
        host = doc.GetElement(host_id)
        if host is None:
            continue
        category = _category_name(host)
        host_type = _type_name(doc, host)
        level_name, elevation = _level(doc, host)
        box = host.get_BoundingBox(None)
        centre = (box.Min + box.Max) * 0.5 if box else DB.XYZ.Zero
        hosts.append({
            'id': value,
            'category': category,
            'type': host_type,
            'mark': _host_mark(host),
            'level': level_name,
            'elevation_mm': elevation,
            'x_mm': centre.X * _FT_TO_MM,
            'y_mm': centre.Y * _FT_TO_MM,
            'rebar_ids': [get_id_value(r.Id) for r in rebars],
            'bars': sum(_quantity(r) for r in rebars),
            'finalized': sum(1 for r in rebars if is_finalized(r)),
            'fingerprint': fingerprint(category, host_type, [_signature(doc, r) for r in rebars]),
        })
    return hosts


def _quantity(rebar):
    try:
        return max(1, int(rebar.Quantity))
    except Exception:
        return 1


def _set(rebar, bip_or_name, value):
    from Autodesk.Revit import DB  # Lazy import
    try:
        if isinstance(bip_or_name, DB.BuiltInParameter):
            param = rebar.get_Parameter(bip_or_name)
        else:
            param = rebar.LookupParameter(bip_or_name)
        if param is None or param.IsReadOnly:
            return False
        return bool(param.Set(value))
    except Exception:
        log_swallowed(_LOG, u'partitions _set')
        return False


def apply(doc, hosts, assignment, ctx):
    """
    Writes Partition, Number of Members and NOSA_Rebar_Show_In_Schedule on every
    non-finalized NOSA bar of the hosts, then renumbers the marks of each partition
    (BS 8666, 01 upwards). Call inside a transaction. Returns a summary dict.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_id_from_int
    import rebar_marking
    by_partition = {}
    skipped = 0
    hidden = 0
    for host in hosts:
        entry = assignment.get(host['id'])
        if entry is None:
            continue
        partition = (entry['partition'] or u'').strip()
        representative = entry['representative']
        for value in host['rebar_ids']:
            rebar = doc.GetElement(element_id_from_int(value))
            if rebar is None:
                continue
            if is_finalized(rebar):
                skipped += 1
                continue
            _set(rebar, DB.BuiltInParameter.NUMBER_PARTITION_PARAM, partition)
            _set(rebar, u'Number of Members', float(entry['members'] if representative else 1))
            _set(rebar, u'NOSA_Rebar_Show_In_Schedule', 1 if representative else 0)
            if not representative:
                hidden += 1
            by_partition.setdefault(partition, []).append(rebar.Id)

    positions = 0
    for partition, ids in sorted(by_partition.items()):
        marking_ctx = dict(ctx or {})
        marking_ctx['mark_prefix'] = partition
        rebar_marking.assign_layers_and_lengths(doc, ids, marking_ctx)
        positions += rebar_marking.deduplicate_and_mark(doc, ids, marking_ctx).get('total_positions', 0)
    return {'partitions': len(by_partition), 'positions': positions,
            'hidden': hidden, 'finalized_skipped': skipped}
