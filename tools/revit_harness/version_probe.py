# -*- coding: utf-8 -*-
"""
Point 11 (user 2026-10-26): the link fixes checked in every Revit version - beam link zones along their spans
(beam_link_zones_probe) and the columns' links fitted to their asked box (link_corner_probe), one run.
Scope (building_test PROBE): doc, ids, _log, _mem, EXT_ROOT, OUT.
"""
import os

_here = os.path.join(EXT_ROOT, 'tools', 'revit_harness')
_log.append(u'== Revit {}'.format(doc.Application.VersionNumber))
for _name in ('beam_link_zones_probe.py', 'link_corner_probe.py'):
    _scope = dict(globals())
    try:
        execfile(os.path.join(_here, _name), _scope)
    except Exception as _e:
        _log.append(u'== {} EXCEPTION {}'.format(_name, _e))
