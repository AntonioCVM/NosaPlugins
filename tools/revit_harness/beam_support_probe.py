# -*- coding: utf-8 -*-
"""Read-only: a beam's clamped axis, spans and the extensions into the columns it frames into.
Scope: doc, EXT_ROOT, PYREVIT, BEAM (id). Result: RESULT."""
import os
import sys
import traceback

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit import DB

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib'),
           os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_log = []
_FT = 304.8
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_id_from_int
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    br = load_module('beam_rebar', os.path.join(lib, 'beam_rebar.py'))
    host = doc.GetElement(element_id_from_int(BEAM))
    raw = br.get_beam_axis(host)
    axis = br._clamp_axis_to_bbox(raw, host)

    def pt(p):
        return u'({:.0f},{:.0f},{:.0f})'.format(p.X * _FT, p.Y * _FT, p.Z * _FT)
    _log.append(u'raw {} -> {}'.format(pt(raw.GetEndPoint(0)), pt(raw.GetEndPoint(1))))
    _log.append(u'clamped {} -> {}'.format(pt(axis.GetEndPoint(0)), pt(axis.GetEndPoint(1))))
    _log.append(u'spans {}'.format(br.beam_spans_mm(host, axis)))
    _log.append(u'extensions {}'.format(br.support_extensions_mm(doc, axis, 48.0)))
except Exception:
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
