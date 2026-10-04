# -*- coding: utf-8 -*-
"""T8.12: Sheet Export Hub drawing check — findings and report dialog (never shown). Result: RESULT."""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
for _asm in ('PresentationCore', 'PresentationFramework', 'WindowsBase', 'System.Xaml', 'System.Windows.Forms'):
    clr.AddReference(_asm)
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
from nosa_utils.bootstrap import load_module
_out = []
try:
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Documentation.panel', 'SheetExportHub.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    ui = load_module('probe_seh_ui', os.path.join(lib, 'ui.py'))
    win = ui.SheetExportHubWindow(doc)
    sheets = sorted(DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet), key=lambda s: s.SheetNumber)[:6]
    _s, labels, findings = win._drawing_findings(sheets)
    from protocol_report_dialog import ProtocolReportDialog
    dlg = ProtocolReportDialog(findings, labels, for_export=True)
    _out.append(u'{} | {} | rows {} | compliant {}'.format(dlg.TxtTitle.Text, dlg.BtnExportCompliant.Content,
                                                         dlg.GridFindings.Items.Count, len(dlg.compliant_labels)))
    dlg.Close()
    win.Close()
except Exception:
    _out.append(traceback.format_exc())
RESULT = u'\n'.join(_out)
