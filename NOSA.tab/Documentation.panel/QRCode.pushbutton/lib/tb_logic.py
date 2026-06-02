# -*- coding: utf-8 -*-
"""
tb_logic.py  v8
Replace the QR-code image inside every unique titleblock family.
Compatible: Revit 2024 / 2025 / 2026 / 2027.
"""

import os
import tempfile

from pyrevit import DB

_VERSION = 'v9'

_QR_SIZE_MM = 24.0
_QR_SIZE_FT = _QR_SIZE_MM / 304.8

# Module-level debug buffer populated by _get_unique_titleblock_families.
_loop_debug = []


def _eid(element_id):
    """
    Return the integer value of a Revit ElementId.

    Revit 2024 and earlier  → ElementId.IntegerValue  (int32)
    Revit 2025 / 2026 / 2027 → ElementId.Value         (int64)

    Using IntegerValue on Revit 2026 raises AttributeError – this helper
    tries both and is the single authoritative way to get the raw id int.
    """
    try:
        return element_id.Value          # Revit 2025+
    except AttributeError:
        return element_id.IntegerValue   # Revit 2024 and earlier


# ---------------------------------------------------------------------------
# IFamilyLoadOptions
# ---------------------------------------------------------------------------

class _LoadOptions(DB.IFamilyLoadOptions):
    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        try:
            overwriteParameterValues.Value = True
        except (AttributeError, TypeError):
            pass
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse,
                            source, overwriteParameterValues):
        try:
            source.Value = DB.FamilySource.Family
            overwriteParameterValues.Value = True
        except (AttributeError, TypeError):
            pass
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
        with DB.Transaction(doc, u'NOSA \u2013 Reload Family') as t:
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
                pass


def _load_family(fam_doc, doc):
    try:
        _reload_in_memory(fam_doc, doc)
        try:
            fam_doc.Close(False)
        except Exception:
            pass
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
    """
    Collect every unique titleblock Family in the document.

    v8: Added per-element debug capture in _loop_debug so that _diagnose()
    can report exactly what happens inside the loop even when all paths fail.
    """
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

                # ── Path 1: direct .Family (FamilySymbol) ────────────────
                fam = None
                fam_err = None
                try:
                    fam = elem.Family
                    step += u':fam={}'.format(
                        u'null' if fam is None else fam.Name)
                except Exception as e1:
                    fam_err = e1
                    step += u':fam_err={}'.format(e1)

                # ── Path 2: .Symbol.Family (FamilyInstance) ───────────────
                if fam is None:
                    try:
                        fam = elem.Symbol.Family
                        step += u':sym_fam={}'.format(
                            u'null' if fam is None else fam.Name)
                    except Exception as e2:
                        step += u':sym_err={}'.format(e2)

                # ── Path 3: GetTypeId → elem → .Family ────────────────────
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

            # Record debug for first 4 elements only (to keep message short)
            if i < 4:
                _loop_debug.append(step)

    except Exception as e_all:
        _loop_debug.append(u'COLLECTOR_ERR:{}'.format(e_all))

    # ── Fallback: sheet-scoped (Revit 2024 original approach) ────────────
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
                            pass
                except Exception:
                    pass
        except Exception:
            pass
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
            pass

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
        pass
    try:
        img.Width  = width_ft
        img.Height = height_ft
        return
    except Exception:
        pass
    for bip, val in [
        (DB.BuiltInParameter.RASTER_SYMBOL_SIZEX, width_ft),
        (DB.BuiltInParameter.RASTER_SYMBOL_SIZEY, height_ft),
    ]:
        try:
            p = img.get_Parameter(bip)
            if p and not p.IsReadOnly:
                p.Set(val)
        except Exception:
            pass


def _place_image(fam_doc, view, img_type_id, centre_xyz, width_ft, height_ft):
    opts    = DB.ImagePlacementOptions(centre_xyz, DB.BoxPlacement.Center)
    new_img = DB.ImageInstance.Create(fam_doc, view, img_type_id, opts)
    _set_size(new_img, width_ft, height_ft)
    return new_img


# ---------------------------------------------------------------------------
# Per-family update
# ---------------------------------------------------------------------------

def _update_family(doc, family, png_path):
    """Returns ('ok'|'skip'|'error', message)."""
    fam_doc = None
    step    = 'EditFamily'
    try:
        fam_doc = doc.EditFamily(family)

        step = 'FindImages'
        qr_imgs, owner_view, pos, w_ft, h_ft = _find_qr_images(fam_doc)
        if not qr_imgs or owner_view is None:
            fam_doc.Close(False)
            return 'skip', u'No image placeholder (skipped)'

        step = 'Transaction'
        with DB.Transaction(fam_doc, u'NOSA \u2013 Replace QR Image') as t:
            t.Start()
            for img in qr_imgs:
                fam_doc.Delete(img.Id)
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
                pass
        return 'error', u'[{}] {}'.format(step, e)


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------

def _diagnose(doc):
    parts = [u'code:' + _VERSION]

    # Include the per-element loop debug captured by _get_unique_titleblock_families
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
    """Return True only if the family name contains 'QR' (case-insensitive)."""
    return 'QR' in name.upper()


def get_png_path(qr_result):
    if isinstance(qr_result, str):
        return qr_result, False
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.close()
    qr_result.save(tmp.name, dpi=(300, 300))
    return tmp.name, True


def run(doc, qr_result):
    """
    Replace the QR image in every unique titleblock family whose name
    contains 'QR'.  Families without 'QR' in the name are silently skipped.
    Returns list of (family_name, status, message)
        status: 'ok' | 'skip' | 'error'
    """
    png_path, owned = get_png_path(qr_result)
    results = []
    try:
        families = _get_unique_titleblock_families(doc)
        if not families:
            diag = _diagnose(doc)
            return [('(none)', 'error',
                     u'No titleblock families found.  [{}]'.format(diag))]

        for fam in families:
            name = fam.Name if fam.Name else u'(unnamed)'
            if not _is_qr_family(name):
                results.append((name, 'skip', u'No contiene "QR" en el nombre (omitida)'))
                continue
            status, msg = _update_family(doc, fam, png_path)
            results.append((name, status, msg))
    finally:
        if owned:
            try:
                os.unlink(png_path)
            except Exception:
                pass
    return results
