# -*- coding: utf-8 -*-
"""
Headless RebarAutomate run, executed inside Revit through pyRevit's
IronPython engine (see run_ra.cs). Drives the plugin's real
Generate -> Select -> Apply path with the values last saved in the
window; only PickObjects and forms.alert are replaced.

Scope variables set by the launcher:
    doc        DB.Document
    MODE       'footings_floors' | 'columns' | 'beams' | 'walls'
    IDS        list of element ids (int)
    CONTROLS   JSON {control name: bool | text} applied to the window first
    OVERRIDES  JSON string merged over the values read from the window
    EXT_ROOT   NOSA.extension folder to load the plugin from
    PYREVIT    pyRevit-Master folder
Result: RESULT (unicode).
"""
import sys
import os
import json
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

from io import StringIO
_out = StringIO()
_old_stdout = sys.stdout
sys.stdout = _out
_log = []

try:
    from nosa_utils.bootstrap import load_module
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Structures.panel', 'Quantities.pulldown',
                          'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))

    def _alert(msg, *args, **kwargs):
        _log.append(u'ALERT: ' + unicode(msg))
        return True
    ui.forms.alert = _alert

    win = ui.RebarAutomateWindow(doc)
    win.Show = lambda: None
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)
    readers = {'footings_floors': win._read_inputs, 'columns': win._read_column_inputs,
               'beams': win._read_beam_inputs, 'walls': win._read_wall_inputs}
    values = readers[MODE]()
    if values is None:
        raise ValueError(u'window inputs rejected')
    values.update(json.loads(OVERRIDES or '{}'))

    class _Ref(object):
        def __init__(self, eid):
            self.ElementId = DB.ElementId(eid)

    class _Selection(object):
        def PickObjects(self, *args):
            return [_Ref(i) for i in IDS]

    class _UIDoc(object):
        Document = doc
        Selection = _Selection()

    class _UIApp(object):
        ActiveUIDocument = _UIDoc()

    win._reinforcement_handler.pending = {'mode': MODE, 'values': values}
    win._reinforcement_handler.Execute(_UIApp())
    result_box = {'footings_floors': 'TxtResult', 'columns': 'TxtColumnResult',
                  'beams': 'TxtBeamResult', 'walls': 'TxtWallResult'}[MODE]
    _log.append(u'RESULT:\n' + unicode(getattr(win, result_box).Text or u''))
    try:
        win.Close()
    except Exception as e:
        _log.append(u'close: {}'.format(e))
except Exception:
    import traceback
    _log.append(u'EXCEPTION:\n' + unicode(traceback.format_exc()))
finally:
    sys.stdout = _old_stdout

RESULT = u'\n'.join(_log) + u'\n--- console ---\n' + _out.getvalue()[-4000:]
