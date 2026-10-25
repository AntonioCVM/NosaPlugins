# -*- coding: utf-8 -*-
"""
rebar_qa.audit itself traced (2026-10-25): its inner calls wrapped so each one's private memory and time go to
OUT.progress as it ends; the audit stops itself past LIMIT_GB. Scope (building_test PROBE): doc, ids, _log, _mem.
"""
import io
import time

from nosa_utils import rebar_qa as qa
from nosa_utils.revit_helpers import get_id_value

LIMIT_GB = 12.0


class Over(Exception):
    pass


def note(line):
    with io.open(OUT + u'.progress', 'a', encoding='utf-8') as fh:
        fh.write(u'{} {}\n'.format(time.strftime('%H:%M:%S'), line))


def traced(name, fn, describe):
    def wrapped(*a, **k):
        p0 = _mem()[0]
        t0 = time.time()
        out = fn(*a, **k)
        p1 = _mem()[0]
        if p1 - p0 > 0.02 or time.time() - t0 > 2.0:
            note(u'   {} {}: {:+.2f} GB -> {:.2f}, {:.1f} s'.format(name, describe(a), p1 - p0, p1, time.time() - t0))
        if p1 > LIMIT_GB:
            raise Over(u'{} {}'.format(name, describe(a)))
        return out
    return wrapped


qa._audit_host = traced(u'_audit_host', qa._audit_host,
                        lambda a: u'{} ({} sets)'.format(get_id_value(a[2].Id), len(a[3])))
qa._joint_pairs = traced(u'_joint_pairs', qa._joint_pairs, lambda a: u'{} parts'.format(len(a[1])))
qa._pairs = traced(u'_pairs', qa._pairs, lambda a: u'{} samples {}'.format(len(a[0]), a[1]))
qa._buildability_host = traced(u'_buildability_host', qa._buildability_host,
                               lambda a: u'{}'.format(get_id_value(a[2].Id)))
qa._crossing = traced(u'_crossing', qa._crossing, lambda a: u'{} sets'.format(len(a[2])))

note(u'== audit trace: start {:.2f} GB'.format(_mem()[0]))
t0 = time.time()
try:
    found = qa.audit(doc, [i for k in ('bases', 'columns', 'beams', 'slabs', 'walls', 'stairs') for i in ids[k]])
    _log.append(u'== audit trace: {} finding(s) in {:.0f} s, {:.2f} GB'.format(len(found), time.time() - t0, _mem()[0]))
except Over as e:
    _log.append(u'== audit trace: stopped over {} GB in {} after {:.0f} s'.format(LIMIT_GB, e, time.time() - t0))
