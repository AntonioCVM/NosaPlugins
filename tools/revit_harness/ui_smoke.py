# -*- coding: utf-8 -*-
"""
Live smoke test inside Revit (test models only): build plugin windows without
showing them, and run the WaffleSlab generator inside a rolled-back
TransactionGroup with warnings swallowed. Same launcher as run_ra.cs.

Scope variables: doc, EXT_ROOT, PYREVIT. Result: RESULT (unicode).
"""
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
_uiapp = UIApplication(doc.Application)
__builtin__.__revit__ = _uiapp

from nosa_utils.bootstrap import load_module

_out = []
TAB = os.path.join(EXT_ROOT, 'NOSA.tab')


def _lib(*parts):
    folder = os.path.join(TAB, *parts)
    lib = os.path.join(folder, 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    return lib


class _Output(object):
    def __init__(self):
        self.lines = []

    def print_md(self, text):
        self.lines.append(unicode(text))


def _window(key, parts, cls_name, *args):
    try:
        lib = _lib(*parts)
        mod = load_module('smoke_' + key, os.path.join(lib, 'ui.py'))
        win = getattr(mod, cls_name)(*args)
        named = len([n for n in dir(win) if n[:3] in ('Txt', 'Cbo', 'Btn', 'Chk', 'Dg_', 'Lst')])
        win.Close()
        _out.append(u'OK   {} window built ({} attrs)'.format(key, named))
        return mod
    except Exception:
        _out.append(u'FAIL {} window:\n{}'.format(key, traceback.format_exc()))
        return None


def _swallow_warnings(sender, args):
    fa = args.GetFailuresAccessor()
    for msg in list(fa.GetFailureMessages()):
        _out.append(u'     failure swallowed: ' + msg.GetDescriptionText())
    fa.DeleteAllWarnings()
    if fa.GetFailureMessages().Count:
        args.SetProcessingResult(DB.FailureProcessingResult.ProceedWithRollBack)


_window('ModelHealthHub', ('Structures.panel', 'Coordination.pulldown', 'ModelHealthHub.pushbutton'),
        'ModelHealthHubWindow', doc)
_window('DataToolsHub', ('Data.panel', 'DataTools.pulldown', 'DataToolsHub.pushbutton'),
        'DataToolsHubWindow', doc)
_window('IssueWorkflowHub', ('Documentation.panel', 'Issue.pulldown', 'IssueWorkflowHub.pushbutton'),
        'IssueWorkflowHubWindow', doc)

# Windows whose SelectionChanged/SelectedIndex moved from XAML to code (NOSA106, 2026-10-02)
import inspect
from pyrevit import forms as _forms
_forms.alert = lambda msg, *a, **k: _out.append(u'     alert: ' + unicode(msg)[:120]) or True
_uidoc = _uiapp.ActiveUIDocument
for parts, cls_name in (
        (('Data.panel', 'ParameterHub.pushbutton'), 'ParameterHubWindow'),
        (('Documentation.panel', 'Sheets.pulldown', 'SheetExportHub.pushbutton'), 'SheetExportHubWindow'),
        (('Documentation.panel', 'Sheets.pulldown', 'SheetHub.pushbutton'), 'SheetHubWindow'),
        (('Documentation.panel', 'Views.pulldown', 'ViewManager.pushbutton'), 'ViewManagerWindow'),
        (('Documentation.panel', 'Views.pulldown', 'ViewOverrides.pushbutton'), 'ViewOverridesWindow'),
        (('Documentation.panel', 'Views.pulldown', 'ViewUtilities.pushbutton'), 'ViewUtilitiesWindow'),
        (('Foundations.panel', 'FootingDesigner.pushbutton'), 'FootingDesignerWindow'),
        (('Foundations.panel', 'PileMaster.pushbutton'), 'PileMasterWindow'),
        (('Foundations.panel', 'PileTools.pulldown', 'AddPileToPilecap.pushbutton'), 'AddPileToPilecapWindow'),
        (('Foundations.panel', 'PileTools.pulldown', 'CreatePilecapType.pushbutton'), 'CreatePilecapWindow'),
        (('Structures.panel', 'Elements.pulldown', 'StructuralTypeManager.pushbutton'), 'StructuralTypeManagerWindow'),
        (('Structures.panel', 'Quantities.pulldown', 'MaterialManager.pushbutton'), 'MaterialManagerWindow')):
    key = parts[-1].replace('.pushbutton', '')
    try:
        lib = _lib(*parts)
        mod = load_module('smoke106_' + key, os.path.join(lib, 'ui.py'))
        cls = getattr(mod, cls_name)
        names = inspect.getargspec(cls.__init__)[0][1:]
        pool = {'doc': doc, 'uidoc': _uidoc, 'output': _Output()}
        win = cls(*[pool.get(n) for n in names])
        combos = [n for n in dir(win) if n[:3] in ('Cbo', 'Cmb', 'cmb') or n.startswith('Combo') or '_Cbo' in n
                  or '_Cmb' in n or '_Combo' in n]
        win.Close()
        _out.append(u'OK   {} built ({} combos)'.format(key, len(combos)))
    except Exception:
        _out.append(u'FAIL {}:\n{}'.format(key, traceback.format_exc()[-600:]))

# SheetExportHub dialogs (NOSAWindow since 2026-10-02)
try:
    sx = _lib('Documentation.panel', 'Sheets.pulldown', 'SheetExportHub.pushbutton')
    naming = load_module('smoke_sx_naming', os.path.join(sx, 'naming.py'))
    for key, cls, args in (
            ('column_chooser_dialog', 'ColumnChooserDialog', (None, [u'Sheet Number', u'Sheet Name'])),
            ('edit_parameters_dialog', 'EditParametersDialog', ([u'Revision', u'Drawn By'], 3)),
            ('confirm_export_dialog', 'ConfirmExportDialog',
             ([], naming.NamingBuilder(), {'pdf': True}, os.environ.get('TEMP', u'C:\\Temp'), {}, False))):
        mod = load_module('smoke_sx_' + key, os.path.join(sx, key + '.py'))
        dlg = getattr(mod, cls)(*args)
        bg = dlg.Resources['BgColor'].Color
        dlg.Close()
        _out.append(u'OK   SheetExportHub {} built (NOSAWindow, BgColor {})'.format(cls, bg))
except Exception:
    _out.append(u'FAIL SheetExportHub dialogs:\n' + traceback.format_exc())

# WaffleSlab (T5.7): window, inline preview, preview window, generator (rolled back)
waffle_parts = ('Structures.panel', 'Elements.pulldown', 'WaffleSlab.pushbutton')
try:
    lib = _lib(*waffle_parts)
    ui = load_module('smoke_waffle_ui', os.path.join(lib, 'ui.py'))
    output = _Output()
    win = ui.WaffleSlabWindow(doc, _uiapp.ActiveUIDocument, output)
    win._refresh_inline_preview()
    params = win._read_params()
    win.Close()
    _out.append(u'OK   WaffleSlab window built, params {}'.format(sorted(params.items())))
    prev = ui._preview.WafflePreviewWindow(params, (0.0, 0.0, 6.0, 6.0), [])
    prev.Close()
    _out.append(u'OK   WaffleSlab preview window built')

    level = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
                   key=lambda l: l.Elevation)[0]
    ft = 1.0 / 0.3048
    x0, y0, x1, y1, z = 200.0, 200.0, 200.0 + 6 * ft, 200.0 + 6 * ft, level.Elevation
    pts = [DB.XYZ(x0, y0, z), DB.XYZ(x1, y0, z), DB.XYZ(x1, y1, z), DB.XYZ(x0, y1, z)]
    boundary = [DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]) for i in range(4)]

    ui._logic.WaffleSlabBuilder  # renamed class must exist
    doc.Application.FailuresProcessing += _swallow_warnings
    tg = DB.TransactionGroup(doc, u'NOSA — smoke (rolled back)')
    tg.Start()
    try:
        builder = ui._logic.WaffleSlabBuilder(doc, params, output)
        ok = builder.generate_waffle_slab(boundary, level)
        topping = builder.topping_slab
        tname = doc.GetElement(topping.GetTypeId()) if topping else None
        from nosa_utils.revit_helpers import element_name
        _out.append(u'{}   WaffleSlab generate: ok={} main={} topping={} voids={} failed={} type={}'.format(
            'OK' if ok and builder.main_slab else 'FAIL', ok, bool(builder.main_slab), bool(topping),
            builder.openings_created, builder.openings_failed, element_name(tname) if tname else None))
        for label, floor in (('ribs', builder.main_slab), ('topping', topping)):
            if floor:
                bb = floor.get_BoundingBox(None)
                _out.append(u'     {}: bottom {:.0f} mm, top {:.0f} mm, joined={}'.format(
                    label, (bb.Min.Z - level.Elevation) * 304.8, (bb.Max.Z - level.Elevation) * 304.8,
                    DB.JoinGeometryUtils.AreElementsJoined(doc, builder.main_slab, topping) if topping else None))
    finally:
        tg.RollBack()
        doc.Application.FailuresProcessing -= _swallow_warnings
    for line in output.lines:
        if u'⚠' in line or u'❌' in line:
            _out.append(u'     log: ' + line[:200])
except Exception:
    _out.append(u'FAIL WaffleSlab:\n' + traceback.format_exc())

RESULT = u'\n'.join(_out)
