# -*- coding: utf-8 -*-
"""T8.13 UI: General Notes dialog apply + drawing check sync warning. Rolled back."""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml'):
    clr.AddReference(_asm)
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
_out = []
group = None
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils import general_notes as gn, sheet_checks
    from nosa_utils import transactions as nosa_tx
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Data.panel', 'ProjectSetupWizard.pushbutton', 'lib')
    gnw = load_module('probe_gnw', os.path.join(lib, 'general_notes_window.py'))
    group = DB.TransactionGroup(doc, u'NOSA test - general notes ui')
    group.Start()
    win = gnw.GeneralNotesWindow(doc)
    _out.append(u'dialog rows {} | concrete box "{}"'.format(len(win._boxes), win._boxes[u'Concrete_Grade'].Text))
    win._boxes[u'Concrete_Grade'].Text = u'C35/45'
    win._boxes[u'Timber_Solid'].Text = u'C24'
    _out.append(u'section boxes: {}'.format(sorted(win._sections)))
    win._sections[u'timber'].IsChecked = False
    win.Apply_Click(None, None)
    from nosa_utils import general_notes_sections as gs
    _out.append(u'state after apply: hidden {} shift {}'.format(gs.read_state(doc)[u'hidden'], gs.read_state(doc)[u'shift']))
    _out.append(u'apply: ' + win.TxtStatus.Text)
    win.Close()
    sheet = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet) if s.SheetNumber == u'0900'][0]
    gn_warn = [f.Message for f in sheet_checks.check_sheet(doc, sheet) if f.Check == u'General notes']
    _out.append(u'check after apply: {} general-notes warnings'.format(len(gn_warn)))
    t = nosa_tx.guard(DB.Transaction(doc, u'NOSA test - edit project info only'))
    t.Start()
    gn.write_project_values(doc, {u'Fire_Resistance': u'120'})
    t.Commit()
    gn_warn = [f.Message for f in sheet_checks.check_sheet(doc, sheet) if f.Check == u'General notes']
    _out.append(u'check after editing Project Information only: {}'.format(gn_warn))
    group.RollBack()
    group = None
    _out.append(u'rolled back')
except Exception:
    _out.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
RESULT = u'\n'.join(_out)
