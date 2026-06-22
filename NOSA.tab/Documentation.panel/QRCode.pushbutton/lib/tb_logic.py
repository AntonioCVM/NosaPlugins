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
# Vector QR mode — FilledRegion-based, no external images in DWG exports
# ---------------------------------------------------------------------------

import math as _math
try:
    from System.Collections.Generic import List as _List
except Exception:
    _List = None  # IronPython without System — fallback handled per-call

_MIN_SEG_FT = 1e-7   # minimum line length to avoid Revit tolerance errors


def _poly_loop(pts_xy):
    """CurveLoop from an ordered list of (x, y) tuples (counter-clockwise = outer)."""
    loop = DB.CurveLoop()
    n = len(pts_xy)
    for i in range(n):
        x0, y0 = pts_xy[i]
        x1, y1 = pts_xy[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        if (dx * dx + dy * dy) < _MIN_SEG_FT * _MIN_SEG_FT:
            continue
        try:
            loop.Append(DB.Line.CreateBound(DB.XYZ(x0, y0, 0), DB.XYZ(x1, y1, 0)))
        except Exception:
            pass
    return loop


def _rect_loop(x0, y0, x1, y1):
    """Axis-aligned rectangle CurveLoop (CCW in Y-up coords)."""
    return _poly_loop([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _circle_poly(cx, cy, r, segs=24):
    """CCW polygon approximation of a circle, returns list of (x, y)."""
    return [
        (cx + r * _math.cos(2 * _math.pi * i / segs),
         cy + r * _math.sin(2 * _math.pi * i / segs))
        for i in range(segs)
    ]


def _hexagon_pts(cx, cy, r):
    """Flat-top hexagon CCW (30° offset), matches NOSA logo orientation."""
    return [
        (cx + r * _math.cos(_math.radians(30 + i * 60)),
         cy + r * _math.sin(_math.radians(30 + i * 60)))
        for i in range(6)
    ]


def _make_list(item_type=None):
    """Return a generic List[CurveLoop] or fall back to a plain Python list."""
    if _List is not None:
        try:
            return _List[DB.CurveLoop]()
        except Exception:
            pass
    return []


def _create_fr(fam_doc, type_id, view_id, loops):
    """Create a FilledRegion from a plain list or System.Collections.Generic.List."""
    if _List is not None:
        try:
            if not isinstance(loops, _List[DB.CurveLoop]):
                net_list = _List[DB.CurveLoop]()
                for lp in loops:
                    net_list.Add(lp)
                loops = net_list
        except Exception:
            pass
    return DB.FilledRegion.Create(fam_doc, type_id, view_id, loops)


def _get_solid_fill_id(fam_doc):
    """Return the ElementId of the solid fill FillPatternElement."""
    for fp in DB.FilteredElementCollector(fam_doc).OfClass(DB.FillPatternElement).ToElements():
        try:
            if fp.GetFillPattern().IsSolidFill:
                return fp.Id
        except Exception:
            pass
    return None


def _get_or_create_frt(fam_doc, name, r, g, b, solid_fill_id):
    """Return ElementId of a solid-colour FilledRegionType, creating it if absent."""
    existing = list(DB.FilteredElementCollector(fam_doc).OfClass(DB.FilledRegionType).ToElements())
    for frt in existing:
        if frt.Name == name:
            return frt.Id
    if not existing:
        return None
    try:
        new_frt = existing[0].Duplicate(name)
    except Exception:
        return existing[0].Id
    color = DB.Color(r, g, b)
    for attr in ('ForegroundPatternColor', 'BackgroundPatternColor'):
        try:
            setattr(new_frt, attr, color)
        except Exception:
            pass
    if solid_fill_id is not None:
        for attr in ('ForegroundPatternId', 'BackgroundPatternId'):
            try:
                setattr(new_frt, attr, solid_fill_id)
            except Exception:
                pass
    return new_frt.Id


def _find_vector_qr_elements(fam_doc):
    """Return all FilledRegions that belong to NOSA_QR_* types."""
    qr_type_ids = set()
    for frt in DB.FilteredElementCollector(fam_doc).OfClass(DB.FilledRegionType).ToElements():
        if frt.Name.startswith('NOSA_QR_'):
            qr_type_ids.add(frt.Id)
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
                pass
        if found_any:
            owner_view = v
            break
    if owner_view is None or mn[0] == float('inf'):
        return None, None, None, None
    cx = (mn[0] + mx[0]) / 2.0
    cy = (mn[1] + mx[1]) / 2.0
    return owner_view, DB.XYZ(cx, cy, 0), mx[0] - mn[0], mx[1] - mn[1]


def _build_vector_qr(fam_doc, view, pos, size_ft, matrix, n,
                     frt_black_id, frt_orange_id, frt_white_id):
    """
    Draw a NOSA-styled QR code as FilledRegion elements inside a family view.

    Colours match the PNG mode:
      - Data modules: square, black
      - Finder pattern rings: circular, orange (outer) + black (inner centre)
      - Logo: orange hexagon + white 'N' bars

    pos      : DB.XYZ  — centre of the QR in the family view plane
    size_ft  : float   — side length in Revit feet (24 mm = _QR_SIZE_FT)
    matrix   : list[list[bool]]  — row 0 = top of QR
    n        : int     — modules per side
    """
    mod = size_ft / float(n)
    orig_x = pos.X - size_ft / 2.0
    orig_y = pos.Y - size_ft / 2.0

    def _mc(row, col):
        """Centre XY of module (row, col). Row 0 = top of QR = max Y in Revit."""
        return (orig_x + (col + 0.5) * mod,
                orig_y + (n - row - 0.5) * mod)

    # Finder-pattern exclusion zones (7×7 corners)
    _FZ = [(0, 0, 6, 6), (0, n - 7, 6, n - 1), (n - 7, 0, n - 1, 6)]

    def _in_finder(r, c):
        for r0, c0, r1, c1 in _FZ:
            if r0 <= r <= r1 and c0 <= c <= c1:
                return True
        return False

    # Logo exclusion zone: circle at QR centre, radius ≈ 4 modules
    logo_r_excl = mod * 4.0
    logo_cx, logo_cy = pos.X, pos.Y

    def _in_logo(r, c):
        cx, cy = _mc(r, c)
        dx, dy = cx - logo_cx, cy - logo_cy
        return (dx * dx + dy * dy) < (logo_r_excl * logo_r_excl)

    # ── 1. Black data modules (one FilledRegion, many CCW rect loops) ─────
    half_m = mod * 0.43  # 0.86 × mod square — similar coverage to Ø0.84 circles
    black_loops = []
    for row in range(n):
        for col in range(n):
            if not matrix[row][col]:
                continue
            if _in_finder(row, col) or _in_logo(row, col):
                continue
            cx, cy = _mc(row, col)
            loop = _rect_loop(cx - half_m, cy - half_m, cx + half_m, cy + half_m)
            black_loops.append(loop)
    if black_loops:
        try:
            _create_fr(fam_doc, frt_black_id, view.Id, black_loops)
        except Exception:
            # Fallback: place individually if batch fails
            for lp in black_loops:
                try:
                    _create_fr(fam_doc, frt_black_id, view.Id, [lp])
                except Exception:
                    pass

    # ── 2. Finder patterns — orange ring + black centre ───────────────────
    segs  = 24
    r_out = mod * 3.3   # outer orange radius
    r_sep = mod * 2.5   # hole (white gap) radius
    r_in  = mod * 1.5   # black inner circle radius

    finder_centers = [(3, 3), (3, n - 4), (n - 4, 3)]
    for (fr_row, fr_col) in finder_centers:
        fcx, fcy = _mc(fr_row, fr_col)

        # Orange donut: outer loop CCW + inner loop CW (= reversed CCW = hole)
        try:
            outer_ccw = _circle_poly(fcx, fcy, r_out, segs)
            inner_cw  = list(reversed(_circle_poly(fcx, fcy, r_sep, segs)))
            orange_loops = [_poly_loop(outer_ccw), _poly_loop(inner_cw)]
            _create_fr(fam_doc, frt_orange_id, view.Id, orange_loops)
        except Exception:
            pass

        # Black inner disc
        try:
            inner_disc = [_poly_loop(_circle_poly(fcx, fcy, r_in, segs))]
            _create_fr(fam_doc, frt_black_id, view.Id, inner_disc)
        except Exception:
            pass

    # ── 3. NOSA logo ──────────────────────────────────────────────────────
    logo_d = mod * 7.0

    # Orange hexagon
    try:
        hex_pts = _hexagon_pts(logo_cx, logo_cy, logo_d * 0.5)
        _create_fr(fam_doc, frt_orange_id, view.Id, [_poly_loop(hex_pts)])
    except Exception:
        pass

    # White 'N' — three separate FilledRegions to avoid self-intersection
    nw  = logo_d * 0.28
    nh  = logo_d * 0.28
    bar = logo_d * 0.085
    rx0, rx1   = logo_cx - nw, logo_cx + nw
    ry_top, ry_bot = logo_cy + nh, logo_cy - nh

    # Left vertical bar (CCW rect)
    try:
        _create_fr(fam_doc, frt_white_id, view.Id,
                   [_rect_loop(rx0, ry_bot, rx0 + bar, ry_top)])
    except Exception:
        pass

    # Right vertical bar (CCW rect)
    try:
        _create_fr(fam_doc, frt_white_id, view.Id,
                   [_rect_loop(rx1 - bar, ry_bot, rx1, ry_top)])
    except Exception:
        pass

    # Diagonal bar (CCW trapezoid: from top-left going CCW)
    try:
        diag_pts = [
            (rx1 - bar, ry_bot), (rx1, ry_bot),
            (rx0 + bar, ry_top), (rx0, ry_top),
        ]
        _create_fr(fam_doc, frt_white_id, view.Id, [_poly_loop(diag_pts)])
    except Exception:
        pass


def _update_family_vector(doc, family, matrix, n):
    """Place a vector QR into a titleblock family. Returns ('ok'|'skip'|'error', msg)."""
    fam_doc = None
    step = 'EditFamily'
    try:
        fam_doc = doc.EditFamily(family)

        step = 'FindAnchor'
        # Primary anchor: existing image placeholder
        qr_imgs, owner_view, pos, w_ft, h_ft = _find_qr_images(fam_doc)

        # Secondary anchor: existing NOSA_QR_ vector elements
        if owner_view is None:
            existing_vec = _find_vector_qr_elements(fam_doc)
            if existing_vec:
                owner_view, pos, w_ft, h_ft = _vector_anchor_from_frs(fam_doc, existing_vec)

        if owner_view is None:
            fam_doc.Close(False)
            return 'skip', u'No hay placeholder de QR (imagen o geometría vectorial)'

        size_ft = w_ft if (w_ft and w_ft > 0) else _QR_SIZE_FT

        step = 'Transaction'
        with DB.Transaction(fam_doc, u'NOSA – Place QR (Vector)') as t:
            t.Start()

            # Remove existing images
            for img in qr_imgs:
                try:
                    fam_doc.Delete(img.Id)
                except Exception:
                    pass

            # Remove existing vector QR elements
            for el in _find_vector_qr_elements(fam_doc):
                try:
                    fam_doc.Delete(el.Id)
                except Exception:
                    pass

            # Ensure FilledRegionType catalogue
            solid_fill_id = _get_solid_fill_id(fam_doc)
            frt_black  = _get_or_create_frt(fam_doc, 'NOSA_QR_Black',   0,   0,   0,   solid_fill_id)
            frt_orange = _get_or_create_frt(fam_doc, 'NOSA_QR_Orange', 255,  95,   0,   solid_fill_id)
            frt_white  = _get_or_create_frt(fam_doc, 'NOSA_QR_White',  255, 255, 255,  solid_fill_id)

            if not frt_black or not frt_orange or not frt_white:
                t.RollBack()
                fam_doc.Close(False)
                return 'error', u'No se pudieron crear los tipos FilledRegion'

            _build_vector_qr(fam_doc, owner_view, pos, size_ft,
                             matrix, n, frt_black, frt_orange, frt_white)
            t.Commit()

        step = 'LoadFamily'
        _load_family(fam_doc, doc)
        return 'ok', u'OK (modo vectorial)'

    except Exception as e:
        if fam_doc:
            try:
                fam_doc.Close(False)
            except Exception:
                pass
        return 'error', u'[{}] {}'.format(step, e)


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


def run(doc, qr_data, mode='png'):
    """
    Replace the QR in every unique titleblock family whose name contains 'QR'.
    Returns list of (family_name, status, message)  status: 'ok' | 'skip' | 'error'

    mode='png'    : qr_data is a PIL Image or temp PNG path (existing behaviour)
    mode='vector' : qr_data is (matrix, n) — draws FilledRegion elements, DWG-safe
    """
    if mode == 'vector':
        matrix, n = qr_data
        families = _get_unique_titleblock_families(doc)
        if not families:
            diag = _diagnose(doc)
            return [('(none)', 'error',
                     u'No se encontraron familias de titleblock.  [{}]'.format(diag))]
        results = []
        for fam in families:
            name = fam.Name if fam.Name else u'(unnamed)'
            if not _is_qr_family(name):
                results.append((name, 'skip', u'No contiene "QR" en el nombre (omitida)'))
                continue
            status, msg = _update_family_vector(doc, fam, matrix, n)
            results.append((name, status, msg))
        return results

    # PNG mode (original behaviour)
    png_path, owned = get_png_path(qr_data)
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
