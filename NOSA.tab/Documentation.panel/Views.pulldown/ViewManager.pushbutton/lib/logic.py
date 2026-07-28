# -*- coding: utf-8 -*-
import os, sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.revit_helpers import get_id_value
from nosa_utils import unit_conversion as _uc10


# ── Create plan views from levels ──────────────────────────────────────────────

def get_levels(doc):
    """[(ElementId, name, elevation_ft)] sorted by elevation."""
    levels = []
    for lv in (DB.FilteredElementCollector(doc)
                 .OfClass(DB.Level).ToElements()):
        try:
            levels.append((lv.Id, lv.Name, lv.Elevation))
        except Exception:
            pass
    levels.sort(key=lambda x: x[2])
    return levels


def get_plan_view_family_types(doc):
    """[(ElementId, label)] for plan-type ViewFamilyTypes."""
    wanted = []
    for name in ('FloorPlan', 'CeilingPlan', 'StructuralPlan', 'AreaPlan'):
        try:
            wanted.append(getattr(DB.ViewFamily, name))
        except AttributeError:
            pass
    result = []
    for vft in (DB.FilteredElementCollector(doc)
                  .OfClass(DB.ViewFamilyType).ToElements()):
        try:
            if vft.ViewFamily not in wanted:
                continue
            fam = str(vft.ViewFamily).split('.')[-1]
            try:
                p = vft.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
                tname = (p.AsString() if p else None) or vft.Name
            except Exception:
                tname = str(get_id_value(vft.Id))
            result.append((vft.Id, u'{} : {}'.format(fam, tname)))
        except Exception:
            pass
    result.sort(key=lambda x: x[1].lower())
    return result


def _existing_view_names(doc):
    names = set()
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            names.add((v.Name or u'').lower())
        except Exception:
            pass
    return names


def _unique_name(base, taken):
    name = base
    n = 1
    while name.lower() in taken:
        n += 1
        name = u'{} ({})'.format(base, n)
    taken.add(name.lower())
    return name


def create_plan_views(doc, level_ids, vft_id, name_pattern,
                      template_id=None, scale=None):
    """
    Create one plan view per level. name_pattern may contain {level}.
    Returns (created, failed, errors).
    """
    created = failed = 0
    errors = []
    taken = _existing_view_names(doc)

    with DB.Transaction(doc, u'NOSA — Create Plan Views') as t:
        t.Start()
        for lid in level_ids:
            try:
                level = doc.GetElement(lid)
                view  = DB.ViewPlan.Create(doc, vft_id, lid)
                base  = (name_pattern or u'{level}').replace(u'{level}', level.Name)
                try:
                    view.Name = _unique_name(base, taken)
                except Exception:
                    pass
                if scale:
                    try:
                        view.Scale = int(scale)
                    except Exception:
                        pass
                if template_id is not None and \
                        template_id != DB.ElementId.InvalidElementId:
                    try:
                        view.ViewTemplateId = template_id
                    except Exception:
                        pass
                created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'Level {}: {}'.format(get_id_value(lid), ex))
        t.Commit()
    return created, failed, errors


# ── Duplicate views ────────────────────────────────────────────────────────────

def _dup_option(mode):
    if mode == 'with_detailing':
        return DB.ViewDuplicateOption.WithDetailing
    if mode == 'dependent':
        return DB.ViewDuplicateOption.AsDependent
    return DB.ViewDuplicateOption.Duplicate


def duplicate_views(doc, view_ids, mode='duplicate', copies=1, name_pattern=u'{name} - Copy {n}'):
    """
    Duplicate each view `copies` times. name_pattern supports {name} and {n}.
    Returns (created, skipped, failed, errors).
    """
    created = skipped = failed = 0
    errors = []
    option = _dup_option(mode)
    taken = _existing_view_names(doc)

    with DB.Transaction(doc, u'NOSA — Duplicate Views') as t:
        t.Start()
        for vid in view_ids:
            try:
                view = doc.GetElement(vid)
                if view is None:
                    skipped += 1
                    continue
                if not view.CanViewBeDuplicated(option):
                    skipped += 1
                    errors.append(u'"{}": cannot be duplicated in this mode.'.format(view.Name))
                    continue
                for n in range(1, int(copies) + 1):
                    new_id  = view.Duplicate(option)
                    new_view = doc.GetElement(new_id)
                    base = (name_pattern or u'{name} - Copy {n}') \
                        .replace(u'{name}', view.Name) \
                        .replace(u'{n}', u'{}'.format(n))
                    try:
                        new_view.Name = _unique_name(base, taken)
                    except Exception:
                        pass
                    created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'View {}: {}'.format(get_id_value(vid), ex))
        t.Commit()
    return created, skipped, failed, errors


# ── Unplaced views (Clean tab) ─────────────────────────────────────────────────

def _placed_view_ids(doc):
    placed = set()
    for sheet in (DB.FilteredElementCollector(doc)
                    .OfClass(DB.ViewSheet).ToElements()):
        try:
            for vid in sheet.GetAllPlacedViews():
                placed.add(get_id_value(vid))
        except Exception:
            pass
    return placed


def unplaced_views(doc):
    """
    Views not placed on any sheet (excluding templates, sheets, schedules,
    legends, and system browser views). Returns list of dicts.
    """
    placed = _placed_view_ids(doc)
    skip_types = set()
    for name in ('Schedule', 'ColumnSchedule', 'PanelSchedule', 'Legend',
                 'DrawingSheet', 'ProjectBrowser', 'SystemBrowser',
                 'Internal', 'Undefined'):
        try:
            skip_types.add(getattr(DB.ViewType, name))
        except AttributeError:
            pass
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate or isinstance(v, DB.ViewSheet):
                continue
            if v.ViewType in skip_types:
                continue
            vid = get_id_value(v.Id)
            if vid in placed:
                continue
            result.append({
                'id_obj': v.Id,
                'id':     vid,
                'name':   v.Name or u'',
                'type':   str(v.ViewType).split('.')[-1],
            })
        except Exception:
            pass
    result.sort(key=lambda r: (r['type'], r['name'].lower()))
    return result


def delete_views(doc, id_objs):
    """Delete views by ElementId. Returns (deleted, failed)."""
    deleted = failed = 0
    with DB.Transaction(doc, u'NOSA — Delete Unplaced Views') as t:
        t.Start()
        for eid in id_objs:
            try:
                doc.Delete(eid)
                deleted += 1
            except Exception:
                failed += 1
        t.Commit()
    return deleted, failed


def sheet_map(doc):
    """
    {view_id_int: {'sheet': u'S-101', 'detail': u'3'}} for every placed view,
    read from viewports so the detail number comes along.
    """
    result = {}
    for vp in (DB.FilteredElementCollector(doc)
                 .OfClass(DB.Viewport).ToElements()):
        try:
            sheet = doc.GetElement(vp.SheetId)
            snum = (sheet.SheetNumber or u'') if sheet else u''
            det = u''
            try:
                p = vp.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
                if p:
                    det = p.AsString() or u''
            except Exception:
                pass
            result[get_id_value(vp.ViewId)] = {'sheet': snum, 'detail': det}
        except Exception:
            pass
    return result


def get_all_view_templates(doc):
    """
    Every view template in the project, any view type, labelled with its type.
    [(ElementId, label)] sorted by name.
    """
    result = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements():
        try:
            if v.IsTemplate:
                result.append((v.Id, u'{}  [{}]'.format(
                    v.Name or u'(unnamed)', str(v.ViewType).split('.')[-1])))
        except Exception:
            pass
    result.sort(key=lambda x: x[1].lower())
    return result


# ── Bulk view properties ───────────────────────────────────────────────────────

def set_view_properties(doc, view_ids, scale=None, detail_level=None,
                        discipline=None):
    """
    Apply scale / detail level / discipline to views. Properties controlled
    by a view template are skipped silently for that view.
    Returns (ok, failed, errors).
    """
    ok = failed = 0
    errors = []
    with DB.Transaction(doc, u'NOSA — Set View Properties') as t:
        t.Start()
        for vid in view_ids:
            try:
                v = doc.GetElement(vid)
                if v is None:
                    failed += 1
                    continue
                touched = False
                if scale:
                    try:
                        v.Scale = int(scale)
                        touched = True
                    except Exception:
                        pass
                if detail_level:
                    try:
                        v.DetailLevel = getattr(DB.ViewDetailLevel, detail_level)
                        touched = True
                    except Exception:
                        pass
                if discipline:
                    try:
                        v.Discipline = getattr(DB.ViewDiscipline, discipline)
                        touched = True
                    except Exception:
                        pass
                if touched:
                    ok += 1
                else:
                    failed += 1
                    errors.append(u'"{}": no property could be set '
                                  u'(template-controlled?).'.format(v.Name))
            except Exception as ex:
                failed += 1
                errors.append(u'View {}: {}'.format(get_id_value(vid), ex))
        t.Commit()
    return ok, failed, errors


# ── 3D per level / drafting views ─────────────────────────────────────────────

def _vft_by_family(doc, family_name):
    try:
        wanted = getattr(DB.ViewFamily, family_name)
    except AttributeError:
        return None
    for vft in (DB.FilteredElementCollector(doc)
                  .OfClass(DB.ViewFamilyType).ToElements()):
        try:
            if vft.ViewFamily == wanted:
                return vft
        except Exception:
            pass
    return None


def create_3d_per_level(doc, name_pattern=u'{level} - 3D'):
    """
    One isometric 3D view per level, section-boxed from the level to the
    next level above (top level gets +4 m). Returns (created, failed, errors).
    """
    vft = _vft_by_family(doc, 'ThreeDimensional')
    if vft is None:
        return 0, 0, [u'No 3D view family type in this project.']
    levels = get_levels(doc)
    if not levels:
        return 0, 0, [u'No levels found.']

    created = failed = 0
    errors = []
    taken = _existing_view_names(doc)
    big = 500.0  # ft half-extent for the section box in plan

    with DB.Transaction(doc, u'NOSA — 3D Views per Level') as t:
        t.Start()
        for i, (lid, lname, elev) in enumerate(levels):
            try:
                top = levels[i + 1][2] if i + 1 < len(levels) else elev + 4.0 * _uc10.M_TO_FT
                view = DB.View3D.CreateIsometric(doc, vft.Id)
                base = (name_pattern or u'{level} - 3D').replace(u'{level}', lname)
                try:
                    view.Name = _unique_name(base, taken)
                except Exception:
                    pass
                bb = DB.BoundingBoxXYZ()
                bb.Min = DB.XYZ(-big, -big, elev)
                bb.Max = DB.XYZ(big, big, top)
                view.SetSectionBox(bb)
                created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}: {}'.format(lname, ex))
        t.Commit()
    return created, failed, errors


def create_drafting_views(doc, count, name_pattern=u'DRAFTING {n}', scale=None):
    """Create N empty drafting views. Returns (created, failed, errors)."""
    vft = _vft_by_family(doc, 'Drafting')
    if vft is None:
        return 0, 0, [u'No drafting view family type in this project.']
    created = failed = 0
    errors = []
    taken = _existing_view_names(doc)

    with DB.Transaction(doc, u'NOSA — Create Drafting Views') as t:
        t.Start()
        for n in range(1, int(count) + 1):
            try:
                view = DB.ViewDrafting.Create(doc, vft.Id)
                base = (name_pattern or u'DRAFTING {n}').replace(u'{n}', u'{}'.format(n))
                try:
                    view.Name = _unique_name(base, taken)
                except Exception:
                    pass
                if scale:
                    try:
                        view.Scale = int(scale)
                    except Exception:
                        pass
                created += 1
            except Exception as ex:
                failed += 1
                errors.append(u'{}'.format(ex))
        t.Commit()
    return created, failed, errors


# ── Preview image ──────────────────────────────────────────────────────────────

def export_view_preview(doc, view, folder):
    """Export a PNG preview of one view. Returns the image path or None."""
    import glob
    from System.Collections.Generic import List as _List
    if not os.path.isdir(folder):
        os.makedirs(folder)
    stem = os.path.join(folder, 'nosa_preview')
    for old in glob.glob(stem + '*.png'):
        try:
            os.remove(old)
        except Exception:
            pass
    opts = DB.ImageExportOptions()
    opts.ExportRange = DB.ExportRange.SetOfViews
    ids = _List[DB.ElementId]()
    ids.Add(view.Id)
    opts.SetViewsAndSheets(ids)
    opts.FilePath  = stem
    opts.ZoomType  = DB.ZoomFitType.FitToPage
    opts.PixelSize = 1000
    opts.HLRandWFViewsFileType = DB.ImageFileType.PNG
    opts.ShadowViewsFileType   = DB.ImageFileType.PNG
    doc.ExportImage(opts)
    produced = glob.glob(stem + '*.png')
    return produced[0] if produced else None
