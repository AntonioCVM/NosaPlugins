# -*- coding: utf-8 -*-
"""Harness: schedule + BVBS export of the test model to OUT_PATH (scope: doc, EXT_ROOT, OUT_PATH)."""
import os
import sys
import clr
clr.AddReference('RevitAPI')
_rb = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel',
                   'RebarAutomate.pushbutton', 'lib')
for p in (os.path.join(EXT_ROOT, 'lib'), _rb):
    if p not in sys.path:
        sys.path.insert(0, p)
_log = []
try:
    import rebar_schedule
    import rebar_export_bvbs
    data = rebar_schedule.generate_schedule_data(doc, batch_id=None, include_finalized=False)
    written, without = rebar_export_bvbs.export_bvbs_file(
        data, OUT_PATH, project_no=doc.ProjectInformation.Number or u'', schedule_no=u'1',
        revision=u'a', steel_grade=u'B500B')
    _log.append(u'positions={} written={} without_geometry={}'.format(len(data), written, without))
    for row in data:
        _log.append(u'{mark} code={shape_code} params={shape_params} n={count} unit={unit_length_mm} legs={legs} s={mandrel_mm}'.format(**row))
except Exception:
    import traceback
    _log.append(traceback.format_exc())
RESULT = u'\n'.join(_log)
