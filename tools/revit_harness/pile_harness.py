# -*- coding: utf-8 -*-
"""
Headless check of the pile tools (T3.5 / T5.5), executed inside Revit through
pyRevit's IronPython engine (see run_pile.cs). Everything runs inside one
TransactionGroup that is rolled back, so the model is left untouched.

Scope variables set by the launcher:
    doc        DB.Document (must be a test model, see _TEST_MODELS)
    EXT_ROOT   NOSA.extension folder (or worktree) to load the plugins from
    PYREVIT    pyRevit-Master folder
Result: RESULT (unicode).
"""
import sys
import os
import imp
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

_TEST_MODELS = (u'Project1', u'Project2', u'Rebar test')

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

_FOUND = os.path.join(EXT_ROOT, 'NOSA.tab', 'Foundations.panel')
_TOOLS = os.path.join(_FOUND, 'PileTools.pulldown')
_log = []


def log(msg):
    _log.append(unicode(msg))


def _old_addpile_point_in_polygon(x, y, polygon):
    # Pre-T5.5 AddPileToPilecap implementation, kept to compare decisions.
    if len(polygon) < 3:
        return False
    n = len(polygon)
    inside = False
    xinters = None
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


def _name(el):
    return DB.Element.Name.GetValue(el)


def _first(collector_iter, pred):
    for e in collector_iter:
        if pred(e):
            return e
    return None


def run():
    if doc.Title not in _TEST_MODELS:
        return u'REFUSED: active document "{}" is not a test model'.format(doc.Title)

    from nosa_utils import pilecap_utils as pu
    from nosa_utils.revit_helpers import get_id_value
    add_logic = imp.load_source('addpiletopilecap_logic',
                                os.path.join(_TOOLS, 'AddPileToPilecap.pushbutton', 'lib', 'logic.py'))
    cap_logic = imp.load_source('createpilecaptype_logic',
                                os.path.join(_TOOLS, 'CreatePilecapType.pushbutton', 'lib', 'logic.py'))
    pm_lib = os.path.join(_FOUND, 'PileMaster.pushbutton', 'lib')
    if pm_lib not in sys.path:
        sys.path.insert(0, pm_lib)
    import logic_coords
    import logic_numbering
    log(u'imports OK (IronPython {})'.format(sys.version.split()[0]))
    log(u'PileMaster shares helpers: coords={} numbering={}'.format(
        logic_coords._ungroup_targets is pu.ungroup_targets,
        logic_numbering._regroup_restore is pu.regroup_restore))

    # T3.5 — config: read-only (legacy file is only read, nothing saved)
    log(u'AddPile last config from empty window cfg: {}'.format(add_logic.load_last_config({})))
    log(u'AddPile has ConfigManager instance: {}'.format(hasattr(add_logic, 'config')))

    pile_sym = _first(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)
                      .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation),
                      lambda s: add_logic.is_allowed_pile_family(s.FamilyName))
    cap_type = _first(DB.FilteredElementCollector(doc).OfClass(DB.FloorType),
                      lambda f: f.IsFoundationSlab)
    level = _first(DB.FilteredElementCollector(doc).OfClass(DB.Level), lambda l: True)
    log(u'using pile "{} : {}", cap "{}", level "{}"'.format(
        pile_sym.FamilyName, _name(pile_sym),
        _name(cap_type), _name(level)))

    tg = DB.TransactionGroup(doc, u'NOSA — pile tools harness (rolled back)')
    tg.Start()
    try:
        # T5.5 — CreatePilecapType irregular cap (validate_cap_polygon uses pilecap_utils)
        center = DB.XYZ(500.0, 500.0, level.Elevation)
        cfg = {'shape_key': 'L', 'param_a': 3, 'param_b': 3, 'param_c': 1, 'param_d': 1,
               'spacing_mm': 1500.0, 'clearance_mm': 450.0, 'cutoff_mm': 75.0,
               'cap_type_id': cap_type.Id, 'pile_type_id': pile_sym.Id, 'level_id': level.Id}
        def _ids():
            return set(get_id_value(e.Id) for e in DB.FilteredElementCollector(doc)
                       .WhereElementIsNotElementType().ToElements())
        before = _ids()
        created, errors = cap_logic.create_pilecap_irregular(doc, cfg, center)
        log(u'CreatePilecapType L cap: created={} errors={}'.format(created, errors))
        new = [e for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType()
               .ToElements() if get_id_value(e.Id) not in before]
        slab = _first(new, lambda e: isinstance(e, DB.Floor))
        piles = [e for e in new if isinstance(e, DB.FamilyInstance)
                 and e.Category and e.Category.Id == slab.Category.Id]
        groups = [e for e in new if isinstance(e, DB.Group)]
        log(u'new elements: slab={} piles={} groups={}'.format(
            slab is not None, len(piles), [_name(g.GroupType) for g in groups]))

        # T5.5 — PileMaster ungroup/regroup round trip
        t = DB.Transaction(doc, u'NOSA — harness regroup')
        t.Start()
        restore = pu.ungroup_targets(doc, piles)
        still_grouped = sum(1 for p in piles
                            if p.GroupId != DB.ElementId.InvalidElementId)
        n = pu.regroup_restore(doc, restore)
        regrouped = sum(1 for p in piles
                        if p.GroupId != DB.ElementId.InvalidElementId)
        t.Commit()
        log(u'ungroup_targets: {} group(s), grouped after ungroup={}, regrouped={} -> '
            u'{} of {} piles back in a group'.format(len(restore), still_grouped, n,
                                                     regrouped, len(piles)))

        # T5.5 — AddPileToPilecap grid on the real slab outline
        solid = add_logic.get_slab_solid_cached(slab)
        face, min_z = add_logic.bottom_face(solid)
        layout = add_logic.compute_slab_layout(face, min_z)
        boundary = add_logic.extract_face_boundary_points(face)
        spacing_ft = 450.0 / 304.8
        clearance_ft = 150.0 / 304.8
        raw = add_logic.generate_rectangular_grid(
            layout['slab_center'], layout['span_dir'], layout['perp_dir'], layout['slab_z'],
            spacing_ft, 10, 10, 9, 9)
        kept = [p for p in raw if add_logic.point_inside_check(
            p.X, p.Y, layout['slab_z'], boundary, face, clearance_ft)]
        mism = sum(1 for p in raw
                   if pu.point_in_polygon(p.X, p.Y, boundary) !=
                   _old_addpile_point_in_polygon(p.X, p.Y, boundary))
        tri = add_logic.generate_triangular_grid(
            layout['slab_center'], layout['span_dir'], layout['perp_dir'], layout['slab_z'],
            spacing_ft, layout['slab_width'], layout['slab_height'], boundary, face, clearance_ft)
        inside_new = sum(1 for p in raw if pu.point_in_polygon(p.X, p.Y, boundary))
        inside_old = sum(1 for p in raw if _old_addpile_point_in_polygon(p.X, p.Y, boundary))
        log(u'AddPile on L slab ({:.2f} x {:.2f} ft, {} outline pts): rectangular 10x10 @450 = {} '
            u'candidates, inside new/old = {}/{}, kept after clearance = {}, triangular kept = {}, '
            u'old/new in-polygon mismatches = {}'.format(
                layout['slab_width'], layout['slab_height'], len(boundary), len(raw),
                inside_new, inside_old, len(kept), len(tri), mism))

        t = DB.Transaction(doc, u'NOSA — harness add piles')
        t.Start()
        made = 0
        for p in kept:
            inst, _top, _mv = add_logic.create_pile_at_point(
                doc, p, pile_sym, level, slab, layout['slab_z'] + 75.0 / 304.8,
                layout['span_rotation_angle'])
            made += 1 if inst else 0
        t.Commit()
        log(u'AddPile create_pile_at_point: {} piles placed'.format(made))
    finally:
        tg.RollBack()
        log(u'TransactionGroup rolled back')

    # T3.5 — the window itself: builds, fills fields from config, never shown or saved
    try:
        add_ui = imp.load_source('addpiletopilecap_ui',
                                 os.path.join(_TOOLS, 'AddPileToPilecap.pushbutton', 'lib', 'ui.py'))
        uidoc = __revit__.ActiveUIDocument
        win = add_ui.AddPileToPilecapWindow(doc, uidoc, None)
        log(u'AddPile window fields: spacing={} embedment={} clearance={} pile={}'.format(
            win.TxtSpacing.Text, win.TxtEmbedment.Text, win.TxtClearance.Text,
            win.CboPileType.SelectedItem))
    except Exception:
        log(u'AddPile window FAILED: ' + traceback.format_exc())
    return u'OK'


try:
    status = run()
except Exception:
    status = u'ERROR\n' + traceback.format_exc()
RESULT = status + u'\n' + u'\n'.join(_log)
