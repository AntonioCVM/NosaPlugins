# -*- coding: utf-8 -*-
"""
T7.9 diagnosis: build a curved wall's reinforcement curves and create each group in its own
transaction whose failures roll back (never a dialog); report which groups Revit accepts.
Everything is rolled back. Scope: doc, EXT_ROOT, PYREVIT. Result: RESULT.
"""
import sys
import os
import math
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from Autodesk.Revit.UI import UIApplication
from System.Collections.Generic import List

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

_FT = 304.8
_log = []
_failures = []


class _RollbackOnError(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        accessor.DeleteAllWarnings()
        errors = [f for f in accessor.GetFailureMessages() if f.GetSeverity() != DB.FailureSeverity.Warning]
        if not errors:
            return DB.FailureProcessingResult.Continue
        _failures.append(u'; '.join(f.GetDescriptionText() for f in errors))
        return DB.FailureProcessingResult.ProceedWithRollBack


def guarded(name, action):
    t = DB.Transaction(doc, name)
    ops = t.GetFailureHandlingOptions()
    ops.SetFailuresPreprocessor(_RollbackOnError())
    ops.SetForcedModalHandling(False)
    t.SetFailureHandlingOptions(ops)
    t.Start()
    before = len(_failures)
    try:
        result = action()
    except Exception as e:
        t.RollBack()
        return u'EXC {}'.format(e)
    status = t.Commit()
    if len(_failures) > before:
        return u'ROLLED BACK: ' + _failures[-1][:160]
    return u'ok {} {}'.format(status, result)


def rebar_from(host, bar_type, curves, normal):
    return DBS.Rebar.CreateFromCurves(doc, DBS.RebarStyle.Standard, bar_type, None, None, host, normal,
                                      List[DB.Curve](curves), DBS.RebarHookOrientation.Left,
                                      DBS.RebarHookOrientation.Left, True, True)


group = None
try:
    if u'template' not in doc.Title and u'Project1' not in doc.Title and u'Rebar test' not in doc.Title:
        raise RuntimeError(u'not a test model: ' + doc.Title)
    from nosa_utils.bootstrap import load_module
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    wall_rebar = load_module('wall_rebar', os.path.join(lib, 'wall_rebar.py'))
    engine = load_module('re_engine', os.path.join(lib, 'rebar_engine.py'))
    group = DB.TransactionGroup(doc, u'NOSA test - curved wall parts')
    group.Start()
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.Elevation)
    wall_type = [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
                 if w.Kind == DB.WallKind.Basic and 200.0 <= w.Width * _FT <= 400.0][0]
    holder = {}

    def _make():
        r = 6000.0 / _FT
        arc = DB.Arc.Create(DB.XYZ(r, 0, 0), DB.XYZ(r * math.cos(2.0944), r * math.sin(2.0944), 0),
                            DB.XYZ(r * math.cos(1.0472), r * math.sin(1.0472), 0))
        holder['wall'] = DB.Wall.Create(doc, arc, wall_type.Id, levels[0].Id, 3000.0 / _FT, 0.0, False, True)
        return holder['wall'].Id
    _log.append(u'wall: ' + guarded(u'wall', _make))
    wall = holder['wall']
    bar_type = engine.get_bar_type_by_diameter(doc, 12.0)
    data = wall_rebar.build_wall_reinforcement(
        doc, wall, 30.0, 12.0, 200.0, 12.0, 200.0, both_faces=True, include_ties=True, tie_dia_mm=8.0,
        include_end_ubars=True, ubar_dia_mm=12.0, include_top_ubars=True, stock_length_mm=12000.0,
        lap_length_mm=600.0, horiz_lap_length_mm=600.0, ubar_lap_length_mm=600.0)
    _log.append(u'warnings: {}'.format(data['warnings']))
    _log.append(u'vertical groups {}, horizontal sets {}, ties {}, end U sets {}/bars {}, top U bars {}'.format(
        len(data['vertical_sets']), len(data['horizontal_sets']), len(data['ties']),
        len(data['end_ubars']['sets']), len(data['end_ubars']['bars']), len(data['top_ubars']['bars'])))

    for vs in data['vertical_sets'][:1]:
        def _ff(vs=vs):
            loops = List[DB.CurveLoop]()
            for chain in vs['freeform_bars']:
                loop = DB.CurveLoop()
                for c in chain:
                    loop.Append(c)
                loops.Add(loop)
            res = DBS.Rebar.CreateFreeForm(doc, bar_type, wall, loops)
            return u'{} bars'.format(res[0].NumberOfBarPositions if isinstance(res, tuple) else res.NumberOfBarPositions)
        _log.append(u'vertical freeform: ' + guarded(u'v', _ff))
    for hs in data['horizontal_sets'][:2]:
        def _h(hs=hs):
            rb = rebar_from(wall, bar_type, hs['curves'], hs['normal'])
            rb.GetShapeDrivenAccessor().SetLayoutAsMaximumSpacing(
                hs['spacing_mm'] / _FT, hs['array_length_mm'] / _FT, True, True, True)
            return u'n{} len {:.0f}'.format(rb.NumberOfBarPositions, hs['curves'][0].Length * _FT)
        _log.append(u'horizontal {}: '.format(hs['label']) + guarded(u'h', _h))
    eb = data['end_ubars']['bars']
    end_sets = data['end_ubars']['sets'][:1] or ([{'curves': eb[0]['curves'], 'normal': eb[0]['normal'],
                                                  'spacing_mm': 200.0, 'array_length_mm': 400.0,
                                                  'materialized_bars': eb[:3]}] if eb else [])
    for s in end_sets:
        _log.append(u'end U single bar: ' + guarded(u'u1', lambda s=s: rebar_from(wall, bar_type, s['curves'], s['normal']).Id))
        def _us(s=s):
            rb = rebar_from(wall, bar_type, s['curves'], s['normal'])
            rb.GetShapeDrivenAccessor().SetLayoutAsMaximumSpacing(
                s['spacing_mm'] / _FT, s['array_length_mm'] / _FT, True, True, True)
            return u'n{}'.format(rb.NumberOfBarPositions)
        _log.append(u'end U set: ' + guarded(u'u2', _us))
        def _uff(s=s):
            loops = List[DB.CurveLoop]()
            for b in s['materialized_bars']:
                loop = DB.CurveLoop()
                for c in b['curves']:
                    loop.Append(c)
                loops.Add(loop)
            res = DBS.Rebar.CreateFreeForm(doc, bar_type, wall, loops)
            return u'{}'.format(res)
        _log.append(u'end U freeform: ' + guarded(u'u3', _uff))

        # never set WorkshopInstructions = Bent on arc chains: Revit opens an error dialog
        # that no failures preprocessor catches (2026-10-03)
    tb = data['top_ubars']['bars']
    if tb:
        _log.append(u'top U single: ' + guarded(u't1', lambda: rebar_from(wall, bar_type, tb[0]['curves'], tb[0]['normal']).Id))
    if data['ties']:
        _log.append(u'tie single: ' + guarded(u'tie', lambda: rebar_from(wall, bar_type, data['ties'][0]['curves'], data['ties'][0]['normal']).Id))
except Exception:
    _log.append(u'EXCEPTION:\n' + traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
        _log.append(u'rolled back')

RESULT = u'\n'.join(_log)
