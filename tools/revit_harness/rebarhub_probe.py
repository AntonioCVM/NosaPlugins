# -*- coding: utf-8 -*-
"""RebarHub live probe: BS 8666 load / marks and Rebar Schedule generation, with tracebacks and timings.
Same launcher as run_ra.cs; scope variables: doc, EXT_ROOT, PYREVIT. Result: RESULT."""
import sys
import os
import time
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml'):
    clr.AddReference(_asm)
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

_out = []
try:
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarHub.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    ui = load_module('probe_rebarhub_ui', os.path.join(lib, 'ui.py'))
    from pyrevit import forms
    forms.alert = lambda msg, *a, **k: _out.append(u'alert: ' + unicode(msg)[:300]) or True
    win = ui.RebarHubWindow(doc, UIApplication(doc.Application).ActiveUIDocument)
    win.LogLine = lambda m: _out.append(u'log: ' + unicode(m)[:300])
    for step in ('_bs_load_bars', '_bs_populate_schedule', '_bs_populate_marks'):
        t0 = time.time()
        try:
            getattr(win, step)()
            _out.append(u'OK   {} {:.1f}s'.format(step, time.time() - t0))
        except Exception:
            _out.append(u'FAIL {}:\n{}'.format(step, traceback.format_exc()[-1500:]))
            break
    _out.append(u'bars {}'.format(len(getattr(win, '_bs_bars', []) or [])))
    for g in sorted((getattr(win, '_bs_groups', {}) or {}).values(), key=lambda x: x['mark'])[:8]:
        _out.append(u'  {mark} {diameter_label} x{quantity} shape {shape} L={length_mm} '
                    u'{total_len_m} m {mass_kg} kg | {hosts}'.format(**g))
    t0 = time.time()
    try:
        options = {'group_by': 'host', 'filter_host_bic': None, 'filter_level_id': None,
                   'filter_phase_id': None, 'show_subtotals': True}
        rows, totals = ui._sched_logic.collect_schedule(doc, options)
        _out.append(u'OK   collect_schedule {} rows {:.1f}s'.format(len(rows), time.time() - t0))
        for r in rows[:6]:
            _out.append(u'  {} | {} {} | {} {} n={} cut={} {} {}'.format(
                r.group_str, r.bar_mark_str, r.shape_str, r.dia_str, r.host_level_str, r.n_bars_str,
                r.cut_str, r.total_len_str, r.total_wt_str))
    except Exception:
        _out.append(u'FAIL collect_schedule {:.1f}s:\n{}'.format(time.time() - t0, traceback.format_exc()[-1500:]))
    win.Close()
except Exception:
    _out.append(u'FAIL setup:\n' + traceback.format_exc())
RESULT = u'\n'.join(_out)
