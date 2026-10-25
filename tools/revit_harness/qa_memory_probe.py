# -*- coding: utf-8 -*-
"""
rebar_qa memory per member (2026-10-25): _audit_host and congested_stations run member by member on the
reinforced building of building_test.py (its PROBE), each timed, its private memory read before, after, and after a
full .NET collection (what stays is native or still referenced), with the native work it did counted: centreline
calls, segments, IntersectWithCurve tests, probe lines made, face projections, geometry reads. Stops past LIMIT_GB.
Scope (from building_test): doc, ids, _log, _mem.
"""
import time

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import RebarHostData
import System

from nosa_utils import rebar_qa as qa
from nosa_utils.revit_helpers import element_name, get_id_value

LIMIT_GB = 12.0
COUNT = {}


def counted(name, fn, extra=None):
    def wrapped(*a, **k):
        COUNT[name] = COUNT.get(name, 0) + 1
        out = fn(*a, **k)
        if extra is not None:
            extra(a, out)
        return out
    return wrapped


def _chain_extra(a, out):
    COUNT['segments'] = COUNT.get('segments', 0) + len(out)


def _inside_extra(a, out):
    solids = a[1] or []
    COUNT['lines made'] = COUNT.get('lines made', 0) + 3
    COUNT['IntersectWithCurve (max)'] = COUNT.get('IntersectWithCurve (max)', 0) + 3 * len(solids)


def _cover_extra(a, out):
    COUNT['face projections'] = COUNT.get('face projections', 0) + len(a[1] or [])


qa._chain = counted('centreline calls', qa._chain, _chain_extra)
qa._fine_points = counted('arc samplings', qa._fine_points)
qa._inside = counted('inside tests', qa._inside, _inside_extra)
qa._cover_mm = counted('cover tests', qa._cover_mm, _cover_extra)
qa._solid_faces = counted('geometry reads (faces)', qa._solid_faces)
qa._solids = counted('geometry reads (solids)', qa._solids)


def collected():
    System.GC.Collect()
    System.GC.WaitForPendingFinalizers()
    System.GC.Collect()
    return _mem()[0]


def measure(label, fn):
    COUNT.clear()
    base = collected()
    t0 = time.time()
    fn()
    secs = time.time() - t0
    after = _mem()[0]
    kept = collected()
    _log.append(u'    {:<34} {:6.1f} s  priv {:6.2f} -> {:6.2f} GB ({:+.2f}), after GC {:6.2f} ({:+.2f})  {}'.format(
        label, secs, base, after, after - base, kept, kept - base,
        u', '.join(u'{} {}'.format(k, v) for k, v in sorted(COUNT.items()))))
    return kept


_log.append(u'== QA memory probe (per member)')
hosts = []
for kind in ('bases', 'columns', 'beams', 'slabs', 'walls', 'stairs'):
    hosts.extend((kind, doc.GetElement(i)) for i in ids[kind])
stop = False
for repeat in (1, 2):
    for kind, host in hosts:
        rebars = list(RebarHostData.GetRebarHostData(host).GetRebarsInHost())
        tag = u'{} {} ({} sets, {} bars) run {}'.format(kind[:-1], get_id_value(host.Id), len(rebars),
                                                         sum(r.Quantity for r in rebars), repeat)
        _log.append(u'  ' + tag)
        kept = measure(u'_audit_host', lambda: qa._audit_host(doc, DB, host, rebars, 32.0, qa.AGGREGATE_MM,
                                                              element_name, get_id_value))
        if kind == 'beams':
            kept = measure(u'congested_stations', lambda: qa.congested_stations(doc, host))
        if kept > LIMIT_GB:
            _log.append(u'  stopped: {:.2f} GB over the {:.0f} GB limit'.format(kept, LIMIT_GB))
            stop = True
            break
        if repeat == 2 and kind == 'beams':
            break                       # the repeat only to see whether a second pass adds up
    if stop:
        break


# ---- the rest of audit(): the joint pairs and the buildability checks, as audit() runs them ----
if not stop:
    _log.append(u'== QA memory probe: joints and buildability')
    by_host = {}
    for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
        by_host.setdefault(get_id_value(r.GetHostId()), []).append(r)
    hosts_by_id = dict((get_id_value(h.Id), h) for _k, h in hosts)
    parts = {}
    for hid, h in hosts_by_id.items():
        found, samples, label = qa._audit_host(doc, DB, h, by_host.get(hid, []), 32.0, qa.AGGREGATE_MM,
                                               element_name, get_id_value)
        parts[hid] = (samples, label)
    tol = qa.JOINT_REACH_MM / qa._MM
    pairs = []
    ids_sorted = sorted(parts)
    for i, a in enumerate(ids_sorted):
        for b in ids_sorted[i + 1:]:
            if qa._touch(hosts_by_id[a].get_BoundingBox(None), hosts_by_id[b].get_BoundingBox(None), tol):
                pairs.append((a, b))
    _log.append(u'  {} members, {} touching pairs'.format(len(parts), len(pairs)))
    t_all = time.time()
    worst = (0.0, None)
    base = collected()
    for k, (a, b) in enumerate(pairs):
        p0 = _mem()[0]
        t0 = time.time()
        segs = sum(len(c) for _r, _d, c, _m in parts[a][0] + parts[b][0])
        owner = dict((get_id_value(r.Id), a) for r, _d, _c, _m in parts[a][0])
        owner.update((get_id_value(r.Id), b) for r, _d, _c, _m in parts[b][0])
        found = qa._pairs(parts[a][0] + parts[b][0], u'pair', qa.AGGREGATE_MM, get_id_value, owner)
        p1 = _mem()[0]
        if p1 - p0 > worst[0]:
            worst = (p1 - p0, (a, b, segs, len(found), time.time() - t0))
        if k % 25 == 0:
            _log.append(u'    pair {}/{}: {:.2f} GB, {} segments, {:.1f} s'.format(k, len(pairs), p1, segs,
                                                                                  time.time() - t0))
        if p1 > LIMIT_GB:
            _log.append(u'  stopped in the joint pairs at {:.2f} GB'.format(p1))
            stop = True
            break
    _log.append(u'  joint pairs: {:.0f} s, priv {:.2f} -> {:.2f}, after GC {:.2f}; worst single pair {}'.format(
        time.time() - t_all, base, _mem()[0], collected(), worst))
if not stop:
    base = collected()
    t_all = time.time()
    for hid, h in hosts_by_id.items():
        p0 = _mem()[0]
        t0 = time.time()
        out = qa._buildability_host(doc, DB, h, by_host.get(hid, []), hosts_by_id, by_host, qa.AGGREGATE_MM,
                                    parts[hid][1], get_id_value)
        p1 = _mem()[0]
        if p1 - p0 > 0.05 or time.time() - t0 > 5.0:
            _log.append(u'    buildability {}: {:+.2f} GB, {:.1f} s, {} finding(s)'.format(hid, p1 - p0,
                                                                                       time.time() - t0, len(out)))
        if p1 > LIMIT_GB:
            _log.append(u'  stopped in buildability at {:.2f} GB'.format(p1))
            break
    _log.append(u'  buildability: {:.0f} s, priv {:.2f} -> {:.2f}, after GC {:.2f}'.format(
        time.time() - t_all, base, _mem()[0], collected()))
