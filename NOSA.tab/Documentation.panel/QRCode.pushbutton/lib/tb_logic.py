# -*- coding: utf-8 -*-
"""
tb_logic.py  v11
Replace the QR-code image inside every unique titleblock family.
Compatible: Revit 2024 / 2025 / 2026 / 2027.
Vector mode removed — PNG only.
"""

import os
import tempfile

from Autodesk.Revit import DB
from nosa_utils import unit_conversion as _uc10
from nosa_utils.telemetry import log_swallowed
_LOG = u'qrcode'
_VERSION = 'v11'

_QR_SIZE_MM = 24.0
_QR_SIZE_FT = _QR_SIZE_MM * _uc10.MM_TO_FT

# Module-level debug buffer populated by _get_unique_titleblock_families.
_loop_debug = []


from nosa_utils.revit_helpers import get_id_value, element_name


def _eid(element_id):
    return get_id_value(element_id)


# ---------------------------------------------------------------------------
# IFamilyLoadOptions
# ---------------------------------------------------------------------------

class _LoadOptions(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        try:
            overwriteParameterValues.Value = True
        except (AttributeError, TypeError):
            log_swallowed(_LOG, u'OnFamilyFound')
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse,
                            source, overwriteParameterValues):
        try:
            source.Value = DB.FamilySource.Family
            overwriteParameterValues.Value = True
        except (AttributeError, TypeError):
            log_swallowed(_LOG, u'OnSharedFamilyFound')
        return True


# ---------------------------------------------------------------------------
# Reload helpers
# ---------------------------------------------------------------------------

def _reload_in_memory(fam_doc, doc):
    fam_doc.LoadFamily(doc, _LoadOptions())


def _reload_via_file(fam_doc, doc):
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(suffix='.rfa', prefix='nosa_tb_')
        os.close(fd)
        save_opts = DB.SaveAsOptions()
        save_opts.OverwriteExistingFile = True
        fam_doc.SaveAs(tmp, save_opts)
        fam_doc.Close(False)
        with DB.Transaction(doc, u'NOSA – Reload Family') as t:
            t.Start()
            result = doc.LoadFamily(tmp, _LoadOptions())
            t.Commit()
        if isinstance(result, (list, tuple)):
            ok = bool(result[0])
        else:
            ok = (result is not None)
        if not ok:
            raise RuntimeError('doc.LoadFamily returned False/None')
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                log_swallowed(_LOG, u'_reload_via_file')


def _load_family(fam_doc, doc):
    try:
        _reload_in_memory(fam_doc, doc)
        try:
            fam_doc.Close(False)
        except Exception:
            log_swallowed(_LOG, u'_load_family')
    except Exception as e1:
        try:
            _reload_via_file(fam_doc, doc)
        except Exception as e2:
            raise RuntimeError(
                u'LoadFamily failed.\n  In-memory: {}\n  File-based: {}'.format(e1, e2)
            )


# ---------------------------------------------------------------------------
# Find unique titleblock families
# ---------------------------------------------------------------------------

def _get_unique_titleblock_families(doc):
    global _loop_debug
    _loop_debug = []
    families = {}

    try:
        tb_elems = (DB.FilteredElementCollector(doc)
                    .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                    .ToElements())
        n = len(tb_elems)
        _loop_debug.append(u'n={}'.format(n))

        for i in range(n):
            step = u'[{}]'.format(i)
            try:
                elem = tb_elems[i]
                step += u':got_elem'

                fam = None
                fam_err = None
                try:
                    fam = elem.Family
                    step += u':fam={}'.format(
                        u'null' if fam is None else fam.Name)
                except Exception as e1:
                    fam_err = e1
                    step += u':fam_err={}'.format(e1)

                if fam is None:
                    try:
                        fam = elem.Symbol.Family
                        step += u':sym_fam={}'.format(
                            u'null' if fam is None else fam.Name)
                    except Exception as e2:
                        step += u':sym_err={}'.format(e2)

                if fam is None:
                    try:
                        te = doc.GetElement(elem.GetTypeId())
                        if te is not None:
                            fam = te.Family
                            step += u':tid_fam={}'.format(
                                u'null' if fam is None else fam.Name)
                    except Exception as e3:
                        step += u':tid_err={}'.format(e3)

                if fam is not None:
                    fid = _eid(fam.Id)
                    if fid not in families:
                        families[fid] = fam
                    step += u':added({})'.format(fid)
                else:
                    step += u':no_fam'

            except Exception as e_elem:
                step += u':OUTER_ERR={}'.format(e_elem)

            if i < 4:
                _loop_debug.append(step)

    except Exception as e_all:
        _loop_debug.append(u'COLLECTOR_ERR:{}'.format(e_all))

    if not families:
        _loop_debug.append(u'trying_sheet_fallback')
        try:
            sheets = (DB.FilteredElementCollector(doc)
                      .OfClass(DB.ViewSheet)
                      .ToElements())
            ns = len(sheets)
            for si in range(ns):
                try:
                    sheet = sheets[si]
                    if getattr(sheet, 'IsPlaceholder', False):
                        continue
                    tbs = (DB.FilteredElementCollector(doc, sheet.Id)
                           .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                           .ToElements())
                    for ti in range(len(tbs)):
                        try:
                            tb  = tbs[ti]
                            sym = doc.GetElement(tb.GetTypeId())
                            fam = sym.Family
                            fid = _eid(fam.Id)
                            if fid not in families:
                                families[fid] = fam
                        except Exception:
                            log_swallowed(_LOG, u'_get_unique_titleblock_families')
                except Exception:
                    log_swallowed(_LOG, u'_get_unique_titleblock_families')
        except Exception:
            log_swallowed(_LOG, u'_get_unique_titleblock_families')
        _loop_debug.append(u'sheet_fallback_found:{}'.format(len(families)))

    return list(families.values())


# ---------------------------------------------------------------------------
# Find QR placeholder images inside a family document
# ---------------------------------------------------------------------------

def _find_qr_images(fam_doc):
    all_imgs = (DB.FilteredElementCollector(fam_doc)
                .OfClass(DB.ImageInstance)
                .ToElements())
    candidates = []
    n = len(all_imgs)
    for i in range(n):
        try:
            img = all_imgs[i]
            owner_id = img.OwnerViewId
            if owner_id == DB.ElementId.InvalidElementId:
                continue
            view = fam_doc.GetElement(owner_id)
            if view is None:
                continue
            bb = img.get_BoundingBox(view)
            if bb is None:
                continue
            w = abs(bb.Max.X - bb.Min.X)
            h = abs(bb.Max.Y - bb.Min.Y)
            if w < 1e-9 or h < 1e-9:
                continue
            if not (0.40 < w / h < 2.50):
                continue
            try:
                centre = img.GetLocation(DB.BoxPlacement.Center)
            except Exception:
                centre = None
            if centre is None:
                centre = DB.XYZ(
                    (bb.Min.X + bb.Max.X) / 2.0,
                    (bb.Min.Y + bb.Max.Y) / 2.0,
                    (bb.Min.Z + bb.Max.Z) / 2.0,
                )
            candidates.append((img, view, centre, w, h))
        except Exception:
            log_swallowed(_LOG, u'_find_qr_images')

    if not candidates:
        return [], None, None, None, None

    candidates.sort(key=lambda t: t[3] * t[4], reverse=True)
    img_list           = [c[0] for c in candidates]
    _, view, pos, w, h = candidates[0]
    return img_list, view, pos, w, h


# ---------------------------------------------------------------------------
# ImageType + ImageInstance creation
# ---------------------------------------------------------------------------

def _load_image_type(fam_doc, png_path):
    opts = DB.ImageTypeOptions(png_path, False, DB.ImageTypeSource.Import)
    return DB.ImageType.Create(fam_doc, opts)


def _set_size(img, width_ft, height_ft):
    try:
        img.LockProportions = False
    except Exception:
        log_swallowed(_LOG, u'_set_size')
    try:
        img.Width  = width_ft
        img.Height = height_ft
        return
    except Exception:
        log_swallowed(_LOG, u'_set_size')
    for bip, val in [
        (DB.BuiltInParameter.RASTER_SYMBOL_SIZEX, width_ft),
        (DB.BuiltInParameter.RASTER_SYMBOL_SIZEY, height_ft),
    ]:
        try:
            p = img.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(val)
        except Exception:
            log_swallowed(_LOG, u'_set_size')


def _place_image(fam_doc, view, img_type_id, centre_xyz, width_ft, height_ft):
    opts    = DB.ImagePlacementOptions(centre_xyz, DB.BoxPlacement.Center)
    new_img = DB.ImageInstance.Create(fam_doc, view, img_type_id, opts)
    _set_size(new_img, width_ft, height_ft)
    return new_img


# ---------------------------------------------------------------------------
# Cleanup helpers for any pre-existing NOSA_QR_* vector elements
# (left over from earlier vector-mode attempts)
# ---------------------------------------------------------------------------

def _find_vector_qr_elements(fam_doc):
    """Return FilledRegions that belong to NOSA_QR_* types."""
    qr_type_ids = set()
    for frt in DB.FilteredElementCollector(fam_doc).OfClass(DB.FilledRegionType).ToElements():
        try:
            if element_name(frt).startswith('NOSA_QR_'):
                qr_type_ids.add(frt.Id)
        except Exception:
            log_swallowed(_LOG, u'_find_vector_qr_elements')
    if not qr_type_ids:
        return []
    return [fr for fr in DB.FilteredElementCollector(fam_doc).OfClass(DB.FilledRegion).ToElements()
            if fr.GetTypeId() in qr_type_ids]


def _vector_anchor_from_frs(fam_doc, frs):
    """Compute (view, pos_XYZ, w_ft, h_ft) from existing NOSA_QR_ FilledRegions."""
    views = list(DB.FilteredElementCollector(fam_doc).OfClass(DB.View).ToElements())
    owner_view = None
    mn = [float('inf'), float('inf')]
    mx = [float('-inf'), float('-inf')]
    for v in views:
        found_any = False
        for fr in frs:
            try:
                bb = fr.GetBoundingBox(v)
                if bb:
                    mn[0] = min(mn[0], bb.Min.X)
                    mn[1] = min(mn[1], bb.Min.Y)
                    mx[0] = max(mx[0], bb.Max.X)
                    mx[1] = max(mx[1], bb.Max.Y)
                    found_any = True
            except Exception:
                log_swallowed(_LOG, u'_vector_anchor_from_frs')
        if found_any:
            owner_view = v
            break
    if owner_view is None or mn[0] == float('inf'):
        return None, None, None, None
    cx = (mn[0] + mx[0]) / 2.0
    cy = (mn[1] + mx[1]) / 2.0
    return owner_view, DB.XYZ(cx, cy, 0), mx[0] - mn[0], mx[1] - mn[1]


# ---------------------------------------------------------------------------
# Per-family update (PNG mode)
# ---------------------------------------------------------------------------

def _update_family(doc, family, png_path):
    """Returns ('ok'|'skip'|'error', message)."""
    fam_doc = None
    step    = 'EditFamily'
    try:
        fam_doc = doc.EditFamily(family)

        step = 'FindImages'
        qr_imgs, owner_view, pos, w_ft, h_ft = _find_qr_images(fam_doc)

        # Fallback: use bounding box of any leftover NOSA_QR_* vector elements
        # as the placement anchor, then remove those elements.
        vec_els = []
        if owner_view is None:
            vec_els = _find_vector_qr_elements(fam_doc)
            if vec_els:
                owner_view, pos, w_ft, h_ft = _vector_anchor_from_frs(fam_doc, vec_els)

        if owner_view is None:
            fam_doc.Close(False)
            return 'skip', u'No image placeholder (skipped)'

        step = 'Transaction'
        with DB.Transaction(fam_doc, u'NOSA – Replace QR Image') as t:
            t.Start()
            for img in qr_imgs:
                try:
                    fam_doc.Delete(img.Id)
                except Exception:
                    log_swallowed(_LOG, u'_update_family')
            for el in vec_els:
                try:
                    fam_doc.Delete(el.Id)
                except Exception:
                    log_swallowed(_LOG, u'_update_family')
            img_type = _load_image_type(fam_doc, png_path)
            _place_image(fam_doc, owner_view, img_type.Id, pos,
                         _QR_SIZE_FT, _QR_SIZE_FT)
            t.Commit()

        step = 'LoadFamily'
        _load_family(fam_doc, doc)

        return 'ok', u'OK'

    except Exception as e:
        if fam_doc:
            try:
                fam_doc.Close(False)
            except Exception:
                log_swallowed(_LOG, u'_update_family')
        return 'error', u'[{}] {}'.format(step, e)


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------

def _diagnose(doc):
    parts = [u'code:' + _VERSION]
    if _loop_debug:
        parts.append(u'loop:[' + u' | '.join(_loop_debug) + u']')
    try:
        n_tb = (DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)
                .GetElementCount())
        parts.append(u'OST_TB:{}'.format(n_tb))
    except Exception as e:
        parts.append(u'OST_TB:ERR({})'.format(e))
    return u'  '.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _is_qr_family(name):
    return 'QR' in name.upper()


def get_png_path(qr_result):
    if isinstance(qr_result, str):
        return qr_result, False
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.close()
    qr_result.save(tmp.name, dpi=(300, 300))
    return tmp.name, True


def run(doc, qr_data, mode='png'):
    """
    Replace the QR in every unique titleblock family whose name contains 'QR'.
    Returns list of (family_name, status, message)  status: 'ok' | 'skip' | 'error'
    """
    png_path, owned = get_png_path(qr_data)
    results = []
    try:
        families = _get_unique_titleblock_families(doc)
        if not families:
            diag = _diagnose(doc)
            return [('(none)', 'error',
                     u'No titleblock families found.  [{}]'.format(diag))]
        for fam in families:
            name = getattr(fam, 'Name', None) or u'(unnamed)'
            if not _is_qr_family(name):
                results.append((name, 'skip', u'Name does not contain "QR" — skipped'))
                continue
            status, msg = _update_family(doc, fam, png_path)
            results.append((name, status, msg))
    finally:
        if owned:
            try:
                os.unlink(png_path)
            except Exception:
                log_swallowed(_LOG, u'run')
    return results

