# -*- coding: utf-8 -*-
"""
Where each column-elevation indicator line was put and why (2026-10-26, A9 'runs along bar' on every column stack):
wraps presentation.free_junction and rebar_presentation._mra before the drawings, logging per Multi-Rebar
Annotation its view, its dimension's id (the audit's D<id>), the junction (view mm), whether a clear place was found
and the bars seen near its line. Scope (building_test PROBE): doc, _log, OUT. Writes OUT + '.mra'.
"""
import io

from nosa_utils import presentation
import rebar_presentation as rp
from nosa_utils.revit_helpers import get_id_value

_path = OUT + '.mra'
io.open(_path, 'w', encoding='utf-8').close()
_last = {}
_orig_free = presentation.free_junction
_orig_mra = rp._mra


def _write(s):
    with io.open(_path, 'a', encoding='utf-8') as fh:
        fh.write(s + u'\n')


def free_junction(candidates, direction, span, segments, tol):
    ok = _orig_free(candidates, direction, span, segments, tol)
    p = candidates[0]
    near = []
    for seg in segments:
        if presentation.runs_along(p, direction, span, seg, tol * 3):
            (ax, ay), (bx, by) = seg
            near.append(u'({:.0f},{:.0f})-({:.0f},{:.0f})'.format(ax, ay, bx, by))
    why = []
    if ok is None:
        # what stops each place tried: its x (view mm) and the first bar segment it runs along
        for c in candidates[::3]:
            for seg in segments:
                if presentation.runs_along(c, direction, span, seg, tol):
                    (ax, ay), (bx, by) = seg
                    why.append(u'[{:.0f}: ({:.0f},{:.0f})-({:.0f},{:.0f})]'.format(c[0], ax, ay, bx, by))
                    break
    _last.update(ok=ok, n=len(candidates), tol=tol, span=span, first=p, dir=direction,
                 chosen=candidates[ok] if ok is not None else None, near=why + near[:4], segs=len(segments))
    return ok


def _mra(doc, view, mra_type, rebar, origin, direction, head, leader):
    m = _orig_mra(doc, view, mra_type, rebar, origin, direction, head, leader)
    if u'Column' in (view.Name or u'') or u'Stair' in (view.Name or u''):
        j = rp._xy(view, origin)
        info = dict(_last)
        _last.clear()
        _write(u'{} | mra {} dim {} | rebar {} {} | junction ({:.0f},{:.0f}) dir ({:.2f},{:.2f}) | free {} of {} '
               u'tol {} span {} chosen {} | seen {} near first: {}'.format(
                   view.Name, get_id_value(m.Id) if m else None, get_id_value(m.DimensionId) if m else None,
                   get_id_value(rebar.Id), rp._text(rebar, u'NOSA_Rebar_Layer'), j[0], j[1],
                   info.get('dir', (0, 0))[0], info.get('dir', (0, 0))[1], info.get('ok'), info.get('n'),
                   info.get('tol'), info.get('span'), info.get('chosen'), info.get('segs'),
                   u' '.join(info.get('near', []))))
    return m


presentation.free_junction = free_junction
rp._mra = _mra
_log.append(u'== mra line probe installed -> ' + _path)
