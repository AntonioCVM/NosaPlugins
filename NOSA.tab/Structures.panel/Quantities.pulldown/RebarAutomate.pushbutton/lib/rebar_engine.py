# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Core Engine (Phase 1)
============================================================================

Pure backend module — NO UI. This is the shared library the future
RebarAutomate plugin's ui.py (and any other consumer) will load via:

    from nosa_utils.bootstrap import load_module
    _rebar_engine = load_module(
        'rebar_engine', os.path.join(os.path.dirname(__file__), 'rebar_engine.py'))

No script.py exists yet in this folder on purpose — this pushbutton is
staged as `.nobutton` (not `.pushbutton`) so it registers nothing on the
ribbon until a future phase adds the UI, following the same suffix
convention this extension already uses for retired plugins.

CONTENTS
--------
  SECTION 1 — Geometry & Cover
      Reads a host element's solid geometry, enumerates its planar
      faces, and computes cover-offset points/curves. RebarHostData is
      consulted on a best-effort basis (see the confidence note below).

  SECTION 2 — RebarWrapper (base creator)
      Defensive wrappers around Rebar.CreateFromCurves and
      Rebar.CreateFromRebarShape, plus lookups for RebarBarType (by
      diameter) and RebarShape (by name).

  SECTION 3 — Stock-length splitting & lap engine
      split_rebar_by_stock_length(): the critical core. Splits an
      over-length idealised bar curve into commercial-length segments
      with normative lap splices, and transversely offsets adjacent
      lapped segments so they don't physically coincide in the 3D model.

UNITS
-----
Every public function that takes or returns a *_mm value works in
millimetres at its boundary (matching every other tool in this
extension) and converts to/from Revit's internal feet internally via
_MM_PER_FT. Revit API objects (Curve, XYZ, Face...) are always in feet,
as usual.

API CONFIDENCE — READ BEFORE TESTING
-------------------------------------
Updated after Phase 4's live-fire test on real footings: plain
Rebar.CreateFromCurves calls (no hooks, style=Standard, single-curve
chains) DID work against a live document without a signature error —
that call's parameter order is now CONFIRMED, not just "documented",
for the no-hook case. Confidence per area, highest first:

  HIGH    Solid/Face extraction, XYZ/Transform/Curve math, RebarBarType
          collection by class, Transaction wrapping, and
          Rebar.CreateFromCurves's parameter order for the plain
          (no-hook) case — all exercised against a live document in
          Phase 4.

  MEDIUM  RebarHostData.GetRebarHostData(host) — the factory call itself
          is standard, but this module deliberately does NOT depend on
          any RebarHostData method beyond that (see
          get_rebar_host_data()'s docstring) specifically because its
          further API surface is the part I'm least certain about.

  MEDIUM  RebarHookType.HookAngle (used by get_hook_type_by_angle,
          Phase 5) — a real, documented property, but not yet exercised
          against a live document. If it throws or returns something
          this module doesn't expect, get_hook_type_by_angle simply
          skips that hook type (see its own docstring) rather than
          crashing, but the lookup could then wrongly report "no 90°
          hook type found" even when one exists.

  MEDIUM  Passing start_hook/end_hook (RebarHookType) into
          Rebar.CreateFromCurves — Phase 5.3 root-caused Phase 5's
          horizontal-hook failure (the `normal` argument defines the
          PLANE the shape lies in, not the hook's bend direction — see
          compute_vertical_hook_plane_normal()'s docstring) and fixed
          it for straight bars. Even with the correct plane, live
          testing then showed the TOP mat's hook still pointing the
          wrong way (up instead of down) — a RebarHookOrientation.Left/
          Right ambiguity this project never pinned down. Phase 5.4
          therefore DROPPED this path for mat bars entirely (see
          footing_rebar.py's module docstring — mats now use explicit
          full-depth U-bar leg geometry instead, via add_end_hooks(),
          not RebarHookType). Dowels are the ONLY remaining consumer of
          this path — they were not reported broken, but were also
          never independently re-verified after the plane-normal fix;
          treat a dowel hook result with the same "verify visually"
          caution as before.

  MEDIUM  Rebar.GetShapeDrivenAccessor() /
          ShapeDrivenAccessor.SetLayoutAsMaximumSpacing(...), used by
          RebarWrapper.create_rebar_set — upgraded from LOWEST after
          Phase 5.5's live test: the SET mechanism itself DOES work for
          an open, U-bar-shaped chain (confirming Phase 5.1's failure
          was NOT fundamentally about open vs closed shapes). What
          Phase 5.5 got wrong was the SIGN of the `normal` used as the
          Set's propagation axis for one of the two mat directions —
          see compute_vertical_hook_plane_normal()'s Phase 5.6 note for
          the full handedness explanation, and
          footing_rebar.build_mat_bar_set for the fix (passing
          propagation_reference so the sign is checked, not assumed).
          NOT YET RE-VERIFIED LIVE at time of writing. If mats still
          come out wrong with the corrected sign,
          footing_rebar.build_mat_bar_chains (plain create_from_curves
          in a loop, confirmed working since Phase 5.4) remains the
          fallback.

  MEDIUM  Rebar.CreateFreeForm(Document, RebarBarType, Element,
          IList<CurveLoop>, out RebarFreeFormValidationResult), used by
          RebarWrapper.create_freeform_group — groups several DISTINCT,
          differently-shaped bar curve chains (an irregular floor
          zone's per-row bars, which a Rebar Set cannot represent) into
          ONE MRA-taggable Rebar element. Phase 2.4's FIRST attempt
          guessed an IList<IList<Curve>> overload from written API
          docs and a live TypeError rejected it outright ("expected
          IList[CurveLoop], got List[List[Curve]]") — IronPython does
          not implicitly coerce a nested Python list-of-lists into
          .NET generics. Phase 2.5 fixed this by building the argument
          natively: one DB.CurveLoop() per bar (curves added via
          .Append(), not passed as a plain list — a CurveLoop here is
          just an explicitly-constructed ordered curve chain, it need
          not be closed), collected into a List[DB.CurveLoop]() via
          .Add() rather than the List[T](iterable) constructor form.
          This is now corroborated by a live error telling us the
          exact expected type, not just written docs — upgraded from
          MEDIUM-LOW — but the corrected constructor pattern has not
          yet round-tripped a successful live creation. Every caller
          (floor_rebar.py's irregular-zone path via ui.py) treats a
          None return as expected, not exceptional, and falls back to
          plain create_from_curves per curve group — check
          self.last_error after a None return to see whether this
          specific call is the reason.

Every Revit-API-specific call in this module is wrapped so a signature
mismatch surfaces as a caught exception with `self.last_error` /
a clear return value (None / False), never a bare crash — but that is
damage control, not a substitute for checking Section 2 against your
installed Revit version's SDK help before relying on it.
"""
import math

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from System.Collections.Generic import List

_MM_PER_FT = 304.8


# ══════════════════════════════════════════════════════════════════════════
# SECTION 1 — Geometry & Cover
# ══════════════════════════════════════════════════════════════════════════

class HostFaceInfo(object):
    """
    A single planar face of a host element's solid, with its outward
    normal and a reference point already resolved — everything the cover
    functions below need, so callers don't have to re-derive it.

    Attributes:
        face    (DB.PlanarFace) the Revit face object.
        normal  (DB.XYZ)  outward-facing unit normal, evaluated at the
                 face's UV bounding-box centre. Constant across the face
                 since it is planar by construction (see get_host_faces).
        origin  (DB.XYZ)  the 3D point on the face at that same UV
                 centre — the reference point cover offsets are measured
                 from.
    """
    def __init__(self, face, normal, origin):
        self.face = face
        self.normal = normal
        self.origin = origin


def get_host_solid(host, include_nested=True):
    """
    Return the largest-volume Solid found in a host element's geometry.

    Columns, beams, slabs, and footings normally expose a single solid;
    a family-based host can expose several (nested instance geometry),
    so this picks the largest by volume as the "main" body — a
    reasonable heuristic for host elements, which are not asked to
    resolve multi-solid family geometry precisely at this stage.

    Args:
        host (DB.Element): the host element (column / beam / floor /
            foundation) to read geometry from.
        include_nested (bool): PHASE 3.5.6 item 2 — if False, solids
            found inside a DB.GeometryInstance (a NESTED family
            instance, e.g. piles nested inside a pile-cap family) are
            skipped entirely — only TOP-LEVEL solids are considered.
            Default True preserves this function's original behaviour
            for every existing caller (columns/beams/floors, none of
            which have this problem). See get_isolated_solid_bbox's
            own docstring for why footing/pile-cap callers need False.

    Returns:
        DB.Solid, or None if the element exposes no solid geometry
        (e.g. it is not yet placed, or geometry extraction failed).
    """
    try:
        opts = DB.Options()
        opts.ComputeReferences = True
        opts.DetailLevel = DB.ViewDetailLevel.Fine
        geo = host.get_Geometry(opts)
    except Exception:
        return None
    if geo is None:
        return None

    best, best_vol = None, 0.0
    for obj in geo:
        if isinstance(obj, DB.Solid):
            try:
                if obj.Volume > best_vol:
                    best, best_vol = obj, obj.Volume
            except Exception:
                pass
        elif include_nested and isinstance(obj, DB.GeometryInstance):
            try:
                nested = obj.GetInstanceGeometry()
            except Exception:
                nested = None
            if nested is None:
                continue
            for inner in nested:
                if isinstance(inner, DB.Solid):
                    try:
                        if inner.Volume > best_vol:
                            best, best_vol = inner, inner.Volume
                    except Exception:
                        pass
    return best


class _SimpleBBox(object):
    """Minimal .Min/.Max XYZ container, the same shape as
    Element.get_BoundingBox's own return — used by
    get_isolated_solid_bbox so it's a drop-in replacement wherever
    host.get_BoundingBox(None) was read before."""
    def __init__(self, mn, mx):
        self.Min = mn
        self.Max = mx


def get_isolated_solid_bbox(host):
    """
    PHASE 3.5.6 item 2 — a bounding box derived from ONLY the host's
    OWN top-level Solid (get_host_solid(host, include_nested=False)),
    read from that solid's own Edges — NOT host.get_BoundingBox(None),
    which reflects the combined extent of the WHOLE family instance,
    including any NESTED family instances.

    Root cause this fixes: a pile cap modelled with piles as NESTED
    family instances inside the SAME pile-cap family reports a
    host.get_BoundingBox(None) that extends all the way down to the
    pile tips — every footing_rebar.py Z/X/Y calculation built on that
    bbox (bottom mat elevation, cover offsets, U-bar leg lengths, plan
    extents) inherited that skew, generating reinforcement that spans
    the piles down to their own base instead of just the cap's own
    slab depth. Reading only the top-level solid's own real geometry
    (the cap's own extrusion, per the standard Revit family-modelling
    convention where the cap's own body is a top-level solid and
    nested piles are separate FamilyInstances) isolates the cap from
    whatever is nested inside it, the same "read the real geometry,
    not a value skewed by something else attached to it" pattern
    already applied to columns joined to floors (Solid.Edges Z-extent)
    and to the column's own vertical extent (Base/Top Level+Offset).

    Returns:
        _SimpleBBox (.Min/.Max DB.XYZ), or None if no top-level solid
        is found or it exposes no usable Edges (e.g. a mocked/test
        solid, or an element whose own body genuinely IS the nested
        instance with nothing at the top level) — callers should fall
        back to host.get_BoundingBox(None) in that case, unchanged
        from pre-3.5.6 behaviour.
    """
    solid = get_host_solid(host, include_nested=False)
    if solid is None:
        return None
    try:
        edges = solid.Edges
    except Exception:
        return None

    xs, ys, zs = [], [], []
    try:
        for edge in edges:
            try:
                curve = edge.AsCurve()
            except Exception:
                continue
            if curve is None:
                continue
            for i in (0, 1):
                try:
                    p = curve.GetEndPoint(i)
                except Exception:
                    continue
                xs.append(p.X)
                ys.append(p.Y)
                zs.append(p.Z)
    except Exception:
        return None
    if not xs:
        return None
    return _SimpleBBox(DB.XYZ(min(xs), min(ys), min(zs)), DB.XYZ(max(xs), max(ys), max(zs)))


def get_host_faces(host):
    """
    Every reasonably PLANAR face of the host's main solid, as
    HostFaceInfo objects ready for cover offsetting.

    Curved faces (a circular column, a haunched beam soffit, etc.) are
    deliberately skipped: ComputeNormal() at one UV point is not a
    meaningful "the" normal for a curved face, and cover on curved faces
    needs a different approach (offsetting along the local normal at
    every point, not a single translation) that this module does not
    attempt yet — a documented limitation, not a silent omission.

    Args:
        host (DB.Element): the host element to read faces from.

    Returns:
        list[HostFaceInfo] — empty if the host has no solid or no
        planar faces.
    """
    solid = get_host_solid(host)
    if solid is None:
        return []
    out = []
    for face in solid.Faces:
        if not isinstance(face, DB.PlanarFace):
            continue
        try:
            bbox_uv = face.GetBoundingBox()
            uv_mid = DB.UV(
                (bbox_uv.Min.U + bbox_uv.Max.U) / 2.0,
                (bbox_uv.Min.V + bbox_uv.Max.V) / 2.0)
            normal = face.ComputeNormal(uv_mid).Normalize()
            origin = face.Evaluate(uv_mid)
            out.append(HostFaceInfo(face, normal, origin))
        except Exception:
            continue
    return out


def get_rebar_host_data(doc, host):
    """
    Best-effort lookup of the host's RebarHostData (Revit's structural
    rebar-cover association object, the same one behind the "Rebar
    Cover" interactive tool in the Revit UI).

    Deliberately forgiving: this returns None on ANY failure, including
    a host that simply has no rebar cover configured yet (a completely
    normal case, not an error) and — per this module's API confidence
    note — the case where GetRebarHostData itself doesn't behave as
    expected on a given Revit version. No other function in this module
    depends on a RebarHostData method beyond this factory call
    succeeding; callers that want Revit's own configured cover values
    should read them from the returned object themselves and fall back
    to a caller-supplied default (e.g. from a RebarCoverType) when it is
    None, rather than this module guessing further API surface it
    hasn't verified.

    Args:
        doc  (DB.Document)
        host (DB.Element): host element (column / beam / floor /
            foundation).

    Returns:
        DBS.RebarHostData, or None.
    """
    try:
        return DBS.RebarHostData.GetRebarHostData(host)
    except Exception:
        return None


# PHASE 3.5.3 item 4 — normative fallback when a host has no Rebar
# Cover configured at all (RebarHostData missing, or GetHostCoverType
# returns nothing for the requested face) — a common, completely valid
# state for a model where the "Rebar Cover" tool was never used. NOT a
# user-facing input any more (see ui.py's own Phase 3.5.3 changes) —
# this is a last-resort code default, printed to the console whenever
# it's actually used so a real cover gap doesn't go unnoticed.
DEFAULT_COVER_MM = 40.0


# PHASE 3.5.4 item 1 FIX — RebarHostData.GetHostCoverType(RebarFaceType)
# was abandoned: IronPython could not resolve RebarFaceType from
# Autodesk.Revit.DB.Structure on the live Revit version this was
# tested against, forcing every cover read into the fallback and
# crashing the section preview. CLEAR_COVER_TOP/BOTTOM/OTHER are
# plain BuiltInParameter values exposed DIRECTLY on the host instance
# (visible in the Properties palette as "Clear cover - Top/Bottom/
# Other Faces") — the same underlying cover data, reached through a
# simpler, more standard get_Parameter() call instead of a
# Structure-namespace factory + enum lookup.
_COVER_BIP_BY_FACE = {
    u'Top': u'CLEAR_COVER_TOP',
    u'Bottom': u'CLEAR_COVER_BOTTOM',
    u'Exterior': u'CLEAR_COVER_OTHER',
    u'Other': u'CLEAR_COVER_OTHER',
}


def _material_fck_mpa(doc, material_id):
    """Concrete compressive strength of a material's structural asset, MPa, or None."""
    material = doc.GetElement(material_id) if material_id is not None else None
    if material is None:
        return None
    asset_elem = doc.GetElement(material.StructuralAssetId)
    asset = asset_elem.GetStructuralAsset() if asset_elem is not None else None
    if asset is not None and asset.StructuralAssetClass == DB.StructuralAssetClass.Concrete:
        try:
            fck = DB.UnitUtils.ConvertFromInternalUnits(asset.ConcreteCompression,
                                                        DB.UnitTypeId.Megapascals)
            if fck > 1.0:
                return fck
        except Exception:
            pass
    # UK templates carry the class in the name only ("Concrete - RC32/40").
    from nosa_utils import laps
    return laps.fck_from_material_name(DB.Element.Name.GetValue(material))


def host_fck_mpa(doc, host):
    """fck of the host's structural concrete (instance/type material, or its structural layer), or None."""
    candidates = []
    for elem in (host, doc.GetElement(host.GetTypeId())):
        if elem is None:
            continue
        try:
            param = elem.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
            if param is not None and param.AsElementId() != DB.ElementId.InvalidElementId:
                candidates.append(param.AsElementId())
        except Exception:
            pass
        try:
            structure = elem.GetCompoundStructure()
            if structure is not None:
                index = structure.StructuralMaterialIndex
                if index >= 0:
                    candidates.append(structure.GetMaterialId(index))
                candidates.extend(layer.MaterialId for layer in structure.GetLayers())
        except Exception:
            pass
    for material_id in candidates:
        try:
            fck = _material_fck_mpa(doc, material_id)
        except Exception:
            fck = None
        if fck:
            return fck
    return None


def get_native_cover_mm(doc, host, face_type_name, default_mm=DEFAULT_COVER_MM):
    """
    PHASE 3.5.3/3.5.4/3.5.5 item 4 — read the host's own NATIVE clear
    cover for one face, replacing a manually-typed UI value: "el
    recubrimiento lo dicta el elemento de hormigón", not a text field.

    PHASE 3.5.4 FIX — reads host.get_Parameter(BuiltInParameter.
    CLEAR_COVER_TOP/BOTTOM/OTHER) directly instead of
    RebarHostData.GetHostCoverType(RebarFaceType) (Phase 3.5.3):
    IronPython failed to resolve RebarFaceType from
    Autodesk.Revit.DB.Structure live, so every call fell through to
    the fallback.

    PHASE 3.5.5 FIX — CLEAR_COVER_TOP/BOTTOM/OTHER are
    StorageType.ElementId parameters: their value is a reference to a
    RebarCoverType ELEMENT, not a raw distance. Reading them with
    param.AsDouble() (Phase 3.5.4) returned 0/garbage for every
    configured cover, flooding the console with "not configured"
    warnings and silently forcing every cover to the 40mm fallback —
    the actual value was one level of indirection away the whole time.
    Fixed to resolve param.AsElementId() through doc.GetElement(...)
    to the real RebarCoverType, then read ITS OWN CoverDistance.

    Args:
        doc            (DB.Document) — now genuinely required, to
                       resolve the RebarCoverType ElementId.
        host           (DB.Element): host element (column / floor /
                       foundation).
        face_type_name (unicode): 'Top', 'Bottom', or 'Exterior' —
                       mapped to the matching BuiltInParameter via
                       _COVER_BIP_BY_FACE.
        default_mm     (float): normative fallback if native cover
                       isn't configured or unreadable, mm.

    Returns:
        float, mm — the host's real configured clear cover for that
        face, or default_mm (with a console warning) if unavailable.
    """
    try:
        bip_name = _COVER_BIP_BY_FACE.get(face_type_name)
        if bip_name is None:
            raise ValueError(u'no BuiltInParameter mapping for face {!r}'.format(face_type_name))
        bip = getattr(DB.BuiltInParameter, bip_name)
        param = host.get_Parameter(bip)
        if param is None:
            raise ValueError(u'this element has no {} parameter'.format(bip_name))
        cover_type_id = param.AsElementId()
        if cover_type_id is None or cover_type_id == DB.ElementId.InvalidElementId:
            raise ValueError(u'{} has no RebarCoverType assigned'.format(bip_name))
        cover_type = doc.GetElement(cover_type_id)
        if cover_type is None:
            raise ValueError(u'{} references a RebarCoverType that no longer exists'
                              .format(bip_name))
        cover_ft = cover_type.CoverDistance
        if cover_ft is None or cover_ft <= 0:
            raise ValueError(u'{}\'s RebarCoverType has a non-positive CoverDistance'
                              .format(bip_name))
        return cover_ft * _MM_PER_FT
    except Exception as e:
        print(u'WARNING [rebar_engine]: could not read native clear cover for the '
              u'{} face ({}) — using normative fallback {:.0f}mm. Set "Clear cover - '
              u'{} Face(s)" on this element in Revit for an accurate value.'.format(
                  face_type_name, e, default_mm, face_type_name))
        return default_mm


def compute_cover_point(face_info, cover_mm):
    """
    A point offset inward from a host face by cover_mm, along that
    face's normal — the geometric "raw geometry minus cover" the brief
    asks for. This is the position where a reinforcement bar's outer
    face should sit relative to that face of the host.

    Args:
        face_info (HostFaceInfo): from get_host_faces().
        cover_mm  (float): cover distance in millimetres.

    Returns:
        DB.XYZ
    """
    cover_ft = cover_mm / _MM_PER_FT
    return face_info.origin - face_info.normal.Multiply(cover_ft)


def offset_curve_inward(curve, face_info, cover_mm):
    """
    Offset an entire curve inward from a host face by cover_mm, along
    that face's normal — used to derive a bar's working line from a
    face-aligned reference curve (e.g. a beam's bottom-face edge,
    already a Curve) rather than a single point.

    Args:
        curve     (DB.Curve): reference curve, typically lying on or
            near face_info's face.
        face_info (HostFaceInfo): from get_host_faces().
        cover_mm  (float): cover distance in millimetres.

    Returns:
        DB.Curve — a new, transformed curve (curves are immutable in
        the Revit API).
    """
    cover_ft = cover_mm / _MM_PER_FT
    shift = face_info.normal.Multiply(-cover_ft)
    transform = DB.Transform.CreateTranslation(shift)
    return curve.CreateTransformed(transform)


def find_foundation_below(doc, x_ft, y_ft, base_z_ft, search_depth_ft=10.0, tol_ft=0.01):
    """
    PHASE F7.18 (2026-09-02, explicit user request — "Starter bars con
    forma de L en columnas y muros... unidas a la cimentación... zapata
    aislada, solera o zapata corrida") — finds whichever foundation
    element sits directly below a given point: an isolated OR wall/strip
    footing (both share OST_StructuralFoundation in Revit — a
    DB.WallFoundation is a distinct class but the SAME category, so one
    collector covers both) or a floor/mat slab (OST_Floors, e.g. a
    "solera"). Generalises column_rebar.find_floor_split_elevations_ft's
    own bbox-based "does this host's plan footprint contain this point"
    pattern to foundation detection for starter bars generated from a
    column/wall's own base, reaching DOWN into whatever's below it —
    the mirror image of footing_rebar.build_dowel_curves, which is
    generated from the FOOTING's own side instead.

    DISCLOSED SIMPLIFICATION: plan footprint tested via the element's
    GLOBAL BOUNDING BOX, not its exact polygon/host boundary — same
    established tradeoff as every other bbox-based host query in this
    project (find_floor_split_elevations_ft included). Also assumes a
    flat (non-sloped) foundation top/bottom, matching footing_rebar.
    get_footing_bottom_face's own -0.7 Z-normal scope.

    Args:
        doc               (DB.Document)
        x_ft, y_ft         (float): the point to search below, project
                          coordinates, ft.
        base_z_ft           (float): the column/wall's own base
                          elevation, ft — only a foundation whose own
                          TOP sits at or just below this (never above
                          it) is considered a match.
        search_depth_ft       (float): how far below base_z_ft to look,
                          ft — default 10ft (~3m), generous for any
                          normal footing/slab depth.
        tol_ft                  (float): bounding-box/elevation
                          tolerance, ft — default ~3mm, matching
                          find_floor_split_elevations_ft's own
                          _OST_FLOORS_TOL_FT.

    Returns:
        DB.Element (the closest match — highest top Z at or below
        base_z_ft — if more than one candidate's bbox contains the
        point), or None if nothing was found.
    """
    best, best_top = None, None
    for cat in (DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_Floors):
        collector = DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType()
        for elem in collector:
            try:
                bbox = elem.get_BoundingBox(None)
            except Exception:
                bbox = None
            if bbox is None:
                continue
            if not (bbox.Min.X - tol_ft <= x_ft <= bbox.Max.X + tol_ft and
                    bbox.Min.Y - tol_ft <= y_ft <= bbox.Max.Y + tol_ft):
                continue
            elem_top = bbox.Max.Z
            if elem_top > base_z_ft + tol_ft:
                continue  # floats above the base — not actually underneath it
            if elem_top < base_z_ft - search_depth_ft:
                continue  # too far below to plausibly be what this base rests on
            if best is None or elem_top > best_top:
                best, best_top = elem, elem_top
    return best


def build_starter_into_foundation(doc, x_ft, y_ft, base_z_ft,
                                   anchor_length_mm, splice_length_mm,
                                   cover_mm, search_depth_ft=10.0, hook_dir=None,
                                   bar_diameter_mm=None):
    """
    PHASE F7.18 (2026-09-02) — ONE straight vertical starter Line
    reaching from a detected foundation's own bottom-face elevation
    (offset inward by cover_mm — "resting on the bottom mat", the SAME
    phrase and convention footing_rebar.build_dowel_curves' own
    docstring uses) UP to splice_length_mm above the foundation's own TOP,
    whatever the foundation depth (2026-09-29: the old anchor + splice sum
    measured from the bottom left a 900 mm pile cap only 140 mm of lap
    above it). The embedded length is returned as 'embedded_mm' so callers
    can compare it with anchor_length_mm. The bar stays a plain straight Line here — the 90° hook
    itself is applied by the CALLER at creation time via RebarHookType
    (start_hook=...), matching how _create_dowel_bars already applies
    one to build_dowel_curves' own straight lines; this function has no
    Revit Transaction open and creates nothing.

    Uses the foundation's own BOUNDING BOX minimum Z as its bottom
    elevation (a flat-foundation assumption, consistent with this
    module's and footing_rebar.py's established scope) rather than
    resolving its actual bottom FACE — cheaper, and avoids a second
    CoverGeometryManager/face-classification pass since find_foundation_
    below already read the same bounding box to locate it.

    Args:
        doc                    (DB.Document)
        x_ft, y_ft              (float): the column/wall's own bar
                              position, ft, project coordinates.
        base_z_ft                (float): the column/wall's own base
                              elevation, ft.
        anchor_length_mm            (float): required anchorage, mm —
                              not used for the geometry; callers compare it
                              with the returned 'embedded_mm'.
        splice_length_mm              (float): additional length ABOVE
                              the foundation's own top, mm — the visible
                              splice for the column/wall's own bars.
        cover_mm                        (float): the FOUNDATION's own
                              bottom cover, mm — NOT the column/wall's
                              own cover.
        search_depth_ft                   (float): passed straight to
                              find_foundation_below.

    Returns:
        {'line': DB.Line, 'normal': DB.XYZ, 'foundation': DB.Element}
        — 'normal' is a fixed (0,0,-1) (this module's flat-foundation
        scope, matching footing_rebar.build_dowel_curves' own bottom-
        face normal for a flat footing exactly) — or None if no
        foundation was found below this point (not an error — a column/
        wall position that genuinely doesn't land on a modelled
        foundation).
    """
    foundation = find_foundation_below(doc, x_ft, y_ft, base_z_ft, search_depth_ft)
    if foundation is None:
        return None
    # The foundation's own solid, not its instance bbox: a pile cap's bbox
    # reaches down to the tips of its nested piles (see get_isolated_solid_bbox).
    bbox = get_isolated_solid_bbox(foundation) or foundation.get_BoundingBox(None)
    if bbox is None:
        return None
    bottom_z_ft = bbox.Min.Z
    top_z_ft = bbox.Max.Z
    cover_ft = cover_mm / _MM_PER_FT
    # Rests on the bottom mat (bottom + cover) and always rises splice_length_mm
    # above the foundation's TOP, whatever its depth; the embedded part is the
    # anchorage, reported back so the caller can flag a too-shallow foundation.
    foot_source = None
    if bar_diameter_mm:
        foot_z_ft, foot_source = starter_foot_z(doc, foundation, bbox, cover_mm, bar_diameter_mm)
    else:
        foot_z_ft = bottom_z_ft + cover_ft
    p0 = DB.XYZ(x_ft, y_ft, foot_z_ft)
    p1 = DB.XYZ(x_ft, y_ft, top_z_ft + splice_length_mm / _MM_PER_FT)
    return {'line': DB.Line.CreateBound(p0, p1), 'normal': starter_hook_plane_normal(hook_dir),
            'foundation': foundation, 'foot_source': foot_source,
            'embedded_mm': (top_z_ft - p0.Z) * _MM_PER_FT}


def starter_hook_plane_normal(hook_dir=None):
    """Plane normal for a VERTICAL starter whose 90° start hook (RebarHookOrientation.Left) points along hook_dir.

    The plane must contain the vertical bar, so its normal is horizontal:
    BasisZ x hook_dir. Verified live (Revit 2026, 2026-09-29): with this
    normal and Left orientation the hook foot points along +hook_dir. A
    (0,0,-1) normal is parallel to the bar and Rebar.CreateFromCurves
    returns None. With no hook_dir, any horizontal normal (BasisX) keeps
    the bar valid.
    """
    if hook_dir is None:
        return DB.XYZ.BasisX
    flat = DB.XYZ(hook_dir.X, hook_dir.Y, 0.0)
    if flat.GetLength() < 1e-9:
        return DB.XYZ.BasisX
    return DB.XYZ.BasisZ.CrossProduct(flat.Normalize())


def rebar_bar_plan_points(rebar):
    """Plan position (XY of the vertical leg) and bottom Z of every bar position of a vertical Rebar or Set, ft.

    XY comes from the highest point, which is on the straight vertical leg:
    a hooked bar's first curve is its hook, whose tip lies outside the
    element the bar rises through (this made the no-duplicate check miss
    existing dowels on 2026-09-29).
    """
    points = []
    for i in range(rebar.NumberOfBarPositions):
        curves = rebar.GetTransformedCenterlineCurves(
            False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, i)
        if curves is None or curves.Count == 0:
            continue
        ends = []
        for curve in curves:
            ends.extend([curve.GetEndPoint(0), curve.GetEndPoint(1)])
        top = max(ends, key=lambda p: p.Z)
        bottom = min(ends, key=lambda p: p.Z)
        points.append(DB.XYZ(top.X, top.Y, bottom.Z))
    return points


def unique_plan_points(points, tol_mm=5.0):
    """Drop points that repeat in plan (stacked stock-length segments of one vertical)."""
    tol_ft = tol_mm / _MM_PER_FT
    kept = []
    for p in sorted(points, key=lambda q: q.Z):
        if all(abs(p.X - k.X) > tol_ft or abs(p.Y - k.Y) > tol_ft for k in kept):
            kept.append(p)
    return kept


def build_contact_starters(doc, bar_points, inward_dirs, base_z_ft, main_dia_mm, starter_dia_mm,
                           anchor_length_mm, splice_length_mm, cover_mm, search_depth_ft=10.0):
    """One L-shaped starter per main vertical bar, contact-lapped on its inner side.

    Each starter sits (main_dia + starter_dia) / 2 towards inward_dirs[i] from
    its vertical, i.e. touching it inside the links, and its 90° foot points the
    opposite way (outwards). It is hosted on the foundation found below it.

    Returns {'bars', 'normals', 'hosts', 'skipped', 'short_anchor_mm'}:
    parallel lists for the created positions, the count of positions with no
    foundation below, and the embedded lengths that fall short of
    anchor_length_mm.
    """
    offset_ft = (main_dia_mm + starter_dia_mm) / 2.0 / _MM_PER_FT
    result = {'bars': [], 'normals': [], 'hosts': [], 'skipped': 0, 'short_anchor_mm': [],
              'anchor_length_mm': anchor_length_mm, 'assumed_mat': 0}
    for point, inward in zip(bar_points, inward_dirs):
        x_ft = point.X + inward.X * offset_ft
        y_ft = point.Y + inward.Y * offset_ft
        starter = build_starter_into_foundation(
            doc, x_ft, y_ft, base_z_ft, anchor_length_mm, splice_length_mm, cover_mm,
            search_depth_ft=search_depth_ft, hook_dir=DB.XYZ(-inward.X, -inward.Y, 0.0),
            bar_diameter_mm=starter_dia_mm)
        if starter is None:
            result['skipped'] += 1
            continue
        result['bars'].append(starter['line'])
        result['normals'].append(starter['normal'])
        result['hosts'].append(starter['foundation'])
        if starter.get('foot_source') == 'assumed':
            result['assumed_mat'] += 1
        if starter['embedded_mm'] < anchor_length_mm:
            result['short_anchor_mm'].append(starter['embedded_mm'])
    return result


def _curves_min_corner(curves):
    xs, ys, zs = [], [], []
    for curve in curves:
        for pt in curve.Tessellate():
            xs.append(pt.X); ys.append(pt.Y); zs.append(pt.Z)
    return DB.XYZ(min(xs), min(ys), min(zs))


def realign_closed_loop(doc, rebar, curves, tol_mm=0.05):
    """Move a closed-loop rebar (stirrup/link) back onto the curves it was created from.

    Revit re-fits a closed loop to its catalogue shape and shifts the whole
    loop by half a bar diameter, outwards from the FIRST segment (verified
    live in Revit 2026, 2026-09-29: an H8 beam stirrup asked at 40 mm clear
    cover came out at 36/44). Moving it back is stable across host edits.
    Open shapes are left alone. Must run inside an open transaction.
    """
    if rebar is None or not curves:
        return
    first, last = curves[0].GetEndPoint(0), curves[-1].GetEndPoint(1)
    if first.DistanceTo(last) > 1e-6:
        return
    doc.Regenerate()
    placed = rebar.GetTransformedCenterlineCurves(
        False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0)
    delta = _curves_min_corner(curves) - _curves_min_corner(list(placed))
    if delta.GetLength() * _MM_PER_FT > tol_mm:
        DB.ElementTransformUtils.MoveElement(doc, rebar.Id, delta)


def find_columns_above(doc, foundation, tol_mm=15.0):
    """Structural columns whose base rests on this foundation's own top, inside its plan."""
    own = get_isolated_solid_bbox(foundation) or foundation.get_BoundingBox(None)
    if own is None:
        return []
    tol_ft = tol_mm / _MM_PER_FT
    columns = []
    collector = (DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
                 .WhereElementIsNotElementType())
    for column in collector:
        bbox = column.get_BoundingBox(None)
        if bbox is None:
            continue
        cx = (bbox.Min.X + bbox.Max.X) / 2.0
        cy = (bbox.Min.Y + bbox.Max.Y) / 2.0
        if (own.Min.X <= cx <= own.Max.X and own.Min.Y <= cy <= own.Max.Y
                and abs(bbox.Min.Z - own.Max.Z) <= tol_ft):
            columns.append(column)
    return columns


def nosa_bars_in_footprint(doc, element, layers):
    """NOSA Rebar of the given NOSA_Rebar_Layer codes with a bar rising inside element's plan footprint."""
    bbox = element.get_BoundingBox(None)
    if bbox is None:
        return []
    found = []
    for rebar in DB.FilteredElementCollector(doc).OfClass(DBS.Rebar):
        param = rebar.LookupParameter(u'NOSA_Rebar_Layer')
        if param is None or param.AsString() not in layers:
            continue
        if any(bbox.Min.X <= p.X <= bbox.Max.X and bbox.Min.Y <= p.Y <= bbox.Max.Y
               for p in rebar_bar_plan_points(rebar)):
            found.append(rebar)
    return found


def bottom_mat_top_z(doc, foundation):
    """Z (ft) of the top face of the NOSA bottom mat already in this foundation, or None."""
    top = None
    for rebar in DB.FilteredElementCollector(doc).OfClass(DBS.Rebar):
        if rebar.GetHostId() != foundation.Id:
            continue
        param = rebar.LookupParameter(u'NOSA_Rebar_Layer')
        if param is None or param.AsString() not in (u'bottom_x', u'bottom_y'):
            continue
        curves = rebar.GetTransformedCenterlineCurves(
            False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0)
        z = min(p.Z for c in curves for p in c.Tessellate())
        level = z + rebar.GetBendData().BarModelDiameter / 2.0
        top = level if top is None else max(top, level)
    return top


def starter_foot_z(doc, foundation, own_bbox, cover_mm, bar_dia_mm, mat_dias_mm=None):
    """Centreline Z (ft) of a dowel/starter foot resting ON the foundation's bottom mat.

    User decision 2026-09-29 (T2.16): the foot sits on top of the bottom mat,
    not at cover level where it crosses the mat's first layer. mat_dias_mm
    (the X and Y bar diameters, when the mat is generated in the same run)
    wins; otherwise the NOSA bottom mat already in the foundation is read;
    otherwise a two-layer mat of bar_dia_mm is assumed.
    Returns (z_ft, source) with source 'given', 'model' or 'assumed'.

    The value is the TOP of the mat, not the foot's centreline: for a bar
    with a start hook Revit reads the line's start as the hook's outer
    face (measured live 2026-09-30 — a centreline value left the foot one
    radius above the mat).
    """
    if mat_dias_mm:
        return own_bbox.Min.Z + (cover_mm + sum(mat_dias_mm)) / _MM_PER_FT, 'given'
    mat_top = bottom_mat_top_z(doc, foundation)
    if mat_top is not None:
        return mat_top, 'model'
    return own_bbox.Min.Z + (cover_mm + 2.0 * bar_dia_mm) / _MM_PER_FT, 'assumed'


def link_corner_extra_inset_mm(bar_dia_mm, link_dia_mm, link_bend_dia_mm=None):
    """
    Extra inset (mm) of a corner bar nested in its link's bend, beyond
    touching the two straight legs.

    Measured live 2026-09-30 (T2.10b): Revit seats a column's corner
    vertical inside the link's bend (Ø10 link, 40 mm tie mandrel, Ø20 bar
    -> centre 62.9 mm from the face, not 60), so a design that ignores the
    bend is pulled 3 mm inwards and anything lapped against it (dowels)
    clashes. link_bend_dia_mm is the inner mandrel diameter (Revit's
    StirrupTieBendDiameter); None assumes 4 x link diameter.
    """
    bar_r = bar_dia_mm / 2.0
    bend_r = (link_bend_dia_mm if link_bend_dia_mm else 4.0 * link_dia_mm) / 2.0
    if bend_r <= bar_r:
        return 0.0
    return bend_r - (bend_r - bar_r) / math.sqrt(2.0) - bar_r


def pin_rebar_to_host_faces(doc, rebar, host, inset_mm):
    """
    Replace Revit's snaps of this rebar to other bars with a fixed distance
    (inset_mm, to the bar centreline) from the nearest host face. Call inside
    a transaction, after every bar it could snap to exists.

    Measured live 2026-09-30 (T2.10b): a column vertical set snapped to its
    link ends one bar 5 mm inwards (67.9 mm from the face instead of 62.9);
    pinning that handle to the face puts both face sets back symmetric.
    Returns the number of handles re-pinned.
    """
    mgr = rebar.GetRebarConstraintsManager()
    pinned = 0
    for handle in mgr.GetAllHandles():
        current = mgr.GetCurrentConstraintOnHandle(handle)
        if current is None or current.GetConstraintType() != DBS.RebarConstraintType.ToOtherRebar:
            continue
        candidates = [cand for cand in mgr.GetConstraintCandidatesForHandle(handle, host.Id)
                      if cand.GetConstraintType() == DBS.RebarConstraintType.FixedDistanceToHostFace]
        if not candidates:
            continue
        nearest = min(candidates, key=lambda cand: abs(cand.GetDistanceToTargetHostFace()))
        nearest.SetDistanceToTargetHostFace(-inset_mm / _MM_PER_FT)
        if hasattr(mgr, 'SetPreferredConstraint'):
            mgr.SetPreferredConstraint(nearest)
        else:
            mgr.SetPreferredConstraintForHandle(handle, nearest)  # Revit 2024
        pinned += 1
    return pinned


def hook_orientation_left():
    """'Left' hook orientation: RebarHookOrientation up to Revit 2026, RebarTerminationOrientation from 2027."""
    enum = getattr(DBS, 'RebarHookOrientation', None) or DBS.RebarTerminationOrientation
    return enum.Left


def rebar_from_curves(doc, style, bar_type, start_hook, end_hook, host, normal, curves,
                      start_orientation, end_orientation, use_existing_shape, create_new_shape):
    """Rebar.CreateFromCurves across API versions (Revit 2027 takes a BarTerminationsData)."""
    if getattr(DBS, 'RebarHookOrientation', None) is not None:
        return DBS.Rebar.CreateFromCurves(
            doc, style, bar_type, start_hook, end_hook, host, normal, curves,
            start_orientation, end_orientation, use_existing_shape, create_new_shape)
    terminations = DBS.BarTerminationsData(doc)
    if start_hook is not None:
        terminations.HookTypeIdAtStart = start_hook.Id
    if end_hook is not None:
        terminations.HookTypeIdAtEnd = end_hook.Id
    terminations.TerminationOrientationAtStart = start_orientation or hook_orientation_left()
    terminations.TerminationOrientationAtEnd = end_orientation or hook_orientation_left()
    return DBS.Rebar.CreateFromCurves(
        doc, style, bar_type, host, normal, curves, terminations,
        use_existing_shape, create_new_shape)


def point_start_hook(doc, rebar, hook_dir):
    """
    Flip the start hook of a vertical bar if its foot does not point along
    hook_dir (plan vector). Call inside a transaction; returns True if flipped.

    Measured 2026-09-30: the same normal + 'Left' orientation gives feet
    pointing outwards in Revit 2026/2027 but inwards in 2024/2025 (Revit
    stores it as 'Right'), so the foot is checked on the built geometry.
    """
    doc.Regenerate()
    curves = list(rebar.GetCenterlineCurves(False, False, False,
                                            DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0))
    points = [c.GetEndPoint(i) for c in curves for i in (0, 1)]
    if len(points) < 3:
        return False
    top = max(points, key=lambda p: p.Z)
    z_low = min(p.Z for p in points)
    tip = max((p for p in points if abs(p.Z - z_low) < 1e-3),
              key=lambda p: (p.X - top.X) ** 2 + (p.Y - top.Y) ** 2)
    foot = DB.XYZ(tip.X - top.X, tip.Y - top.Y, 0.0)
    if foot.GetLength() < 1e-6 or foot.DotProduct(DB.XYZ(hook_dir.X, hook_dir.Y, 0.0)) >= 0.0:
        return False
    if hasattr(rebar, 'GetHookOrientation'):
        enum = DBS.RebarHookOrientation
        current = rebar.GetHookOrientation(0)
        rebar.SetHookOrientation(0, enum.Right if current == enum.Left else enum.Left)
    else:
        enum = DBS.RebarTerminationOrientation  # Revit 2027
        current = rebar.GetTerminationOrientation(0)
        rebar.SetTerminationOrientation(0, enum.Right if current == enum.Left else enum.Left)
    return True


MIN_STARTER_FOOT_MM = 450.0


def starter_l_curves(line, hook_dir, bar_dia_mm, foundation=None, cover_mm=None):
    """
    [foot, vertical] centreline curves of an L-shaped dowel/starter.

    `line` runs from the top of the mat the foot rests on (its start) up to
    the lap end. The foot is max(450 mm, 12 d) long (IStructE SMDSC 6.7:
    column starters need a horizontal leg of at least 450 mm) along
    hook_dir, shortened only where it would leave the foundation's cover.
    Built as explicit curves, not a hook type, so length and direction are
    the same in every Revit version (T2.18, 2026-09-30).
    Returns (curves, foot_mm).
    """
    radius_ft = bar_dia_mm / 2.0 / _MM_PER_FT
    start, top = line.GetEndPoint(0), line.GetEndPoint(1)
    corner = DB.XYZ(start.X, start.Y, start.Z + radius_ft)
    direction = DB.XYZ(hook_dir.X, hook_dir.Y, 0.0).Normalize()
    foot_ft = max(MIN_STARTER_FOOT_MM, 12.0 * bar_dia_mm) / _MM_PER_FT
    if foundation is not None and cover_mm is not None:
        bbox = get_isolated_solid_bbox(foundation) or foundation.get_BoundingBox(None)
        if bbox is not None:
            inset_ft = (cover_mm + bar_dia_mm / 2.0) / _MM_PER_FT
            for axis, lo, hi in (('X', bbox.Min.X, bbox.Max.X), ('Y', bbox.Min.Y, bbox.Max.Y)):
                d = getattr(direction, axis)
                here = getattr(corner, axis)
                if d > 1e-9:
                    foot_ft = min(foot_ft, (hi - inset_ft - here) / d)
                elif d < -1e-9:
                    foot_ft = min(foot_ft, (here - lo - inset_ft) / -d)
    foot_ft = max(foot_ft, 4.0 * bar_dia_mm / _MM_PER_FT)
    tip = corner + direction.Multiply(foot_ft)
    top = DB.XYZ(top.X, top.Y, top.Z)
    return [DB.Line.CreateBound(tip, corner), DB.Line.CreateBound(corner, top)], foot_ft * _MM_PER_FT


def set_workshop_bent(rebar):
    """
    Workshop Instructions = Bend on a FreeForm bar: with the default "Keep Straight"
    Revit matches every FreeForm bar to shape 00; with Bend it matches the real bent
    shape (U-bars on a skewed edge -> 21). Measured 2026-10-01 in Revit 2026.
    """
    try:
        rebar.GetFreeFormAccessor().WorkshopInstructions = DBS.RebarWorkInstructions.Bent
        return True
    except Exception:
        pass
    try:
        param = rebar.get_Parameter(DB.BuiltInParameter.REBAR_WORKSHOP_INSTRUCTIONS)
        return bool(param is not None and not param.IsReadOnly and param.Set(0))
    except Exception:
        return False


def find_rebar_shape(doc, name):
    """The project's RebarShape called `name` (e.g. u'26'), or None."""
    for shape in DB.FilteredElementCollector(doc).OfClass(DBS.RebarShape):
        try:
            if DB.Element.Name.GetValue(shape) == name:  # .Name fails on RebarShape in IronPython
                return shape
        except Exception:
            continue
    return None


def rebar_from_curves_and_shape(doc, shape, bar_type, host, normal, curves):
    """Rebar.CreateFromCurvesAndShape, no hooks, across API versions; raises if Revit rejects it."""
    if getattr(DBS, 'RebarHookOrientation', None) is not None:
        return DBS.Rebar.CreateFromCurvesAndShape(
            doc, shape, bar_type, None, None, host, normal, curves,
            hook_orientation_left(), hook_orientation_left())
    terminations = DBS.BarTerminationsData(doc)
    return DBS.Rebar.CreateFromCurvesAndShape(
        doc, shape, bar_type, host, normal, curves, terminations)


def _create_rebar(wrapper, style, bar_type, host, normal, curve_list, shape_name):
    """The named shape when asked for and Revit accepts the curves, else CreateFromCurves."""
    if shape_name:
        shape = find_rebar_shape(wrapper.doc, shape_name)
        if shape is not None:
            try:
                rebar = rebar_from_curves_and_shape(
                    wrapper.doc, shape, bar_type, host, normal, curve_list)
                if rebar is not None:
                    return rebar
            except Exception as e:
                wrapper.shape_warning = u'shape {} rejected ({}); created by curves'.format(
                    shape_name, e)
        else:
            wrapper.shape_warning = u'shape {} is not loaded in this project'.format(shape_name)
    return rebar_from_curves(
        wrapper.doc, style, bar_type, None, None, host, normal, curve_list,
        hook_orientation_left(), hook_orientation_left(), True, True)


def find_lapped_circle_shape(doc):
    """The project's closed lapped circular link RebarShape (BS 8666 / ISO 3766 code 75), or None."""
    fallback = None
    for shape in DB.FilteredElementCollector(doc).OfClass(DBS.RebarShape):
        try:
            definition = shape.GetRebarShapeDefinition()
            if not isinstance(definition, DBS.RebarShapeDefinitionByArc):
                continue
            if definition.Type != DBS.RebarShapeDefinitionByArcType.LappedCircle:
                continue
        except Exception:
            continue
        if DB.Element.Name.GetValue(shape) == u'75':  # .Name fails on RebarShape in IronPython
            return shape
        fallback = fallback or shape
    return fallback


class CoverGeometryManager(object):
    """
    Bundles face discovery, best-effort RebarHostData lookup, and
    cover-offset geometry for ONE host element into a single workflow,
    so callers don't have to re-derive the host's solid/faces for every
    cover calculation:

        mgr = CoverGeometryManager(doc, host)
        for face_info in mgr.faces:
            outer_pt = mgr.cover_point(face_info, cover_mm=40)

    Attributes:
        doc             (DB.Document)
        host            (DB.Element)
        solid           (DB.Solid or None) — see get_host_solid().
        faces           (list[HostFaceInfo]) — see get_host_faces().
        rebar_host_data (DBS.RebarHostData or None) — best-effort, see
                         get_rebar_host_data().
    """
    def __init__(self, doc, host):
        self.doc = doc
        self.host = host
        self.solid = get_host_solid(host)
        self.faces = get_host_faces(host)
        self.rebar_host_data = get_rebar_host_data(doc, host)

    def cover_point(self, face_info, cover_mm):
        return compute_cover_point(face_info, cover_mm)

    def cover_curve(self, curve, face_info, cover_mm):
        return offset_curve_inward(curve, face_info, cover_mm)


# ══════════════════════════════════════════════════════════════════════════
# SECTION 2 — RebarWrapper (base creator)
# ══════════════════════════════════════════════════════════════════════════

def get_bar_type_by_diameter(doc, diameter_mm, tolerance_mm=0.5):
    """
    Find the project's RebarBarType whose bar diameter matches
    diameter_mm within tolerance_mm.

    Reads BarDiameter directly when the .NET property is available,
    falling back to the REBAR_BAR_DIAMETER built-in parameter for older
    API surfaces — the same "try the modern property, fall back to the
    built-in parameter" compatibility pattern already used across this
    extension for other year-to-year API differences.

    Args:
        doc           (DB.Document)
        diameter_mm   (float): target bar diameter, e.g. 16 for a 16mm bar.
        tolerance_mm  (float): matching tolerance, default 0.5mm.

    Returns:
        DBS.RebarBarType, or None if no type is within tolerance.
    """
    target_ft = diameter_mm / _MM_PER_FT
    tol_ft = tolerance_mm / _MM_PER_FT
    best, best_diff = None, 1e9

    for bt in DB.FilteredElementCollector(doc).OfClass(DBS.RebarBarType).ToElements():
        dia = None
        try:
            dia = bt.BarDiameter
        except Exception:
            try:
                p = bt.get_Parameter(DB.BuiltInParameter.REBAR_BAR_DIAMETER)
                dia = p.AsDouble() if p else None
            except Exception:
                dia = None
        if dia is None:
            continue
        diff = abs(dia - target_ft)
        if diff < best_diff:
            best, best_diff = bt, diff

    return best if (best is not None and best_diff <= tol_ft) else None


def get_rebar_shape_by_name(doc, name):
    """
    RebarShape element whose Name matches `name` (case-insensitive,
    whitespace-trimmed), or None.

    Args:
        doc  (DB.Document)
        name (unicode): the shape family/type name to look for, e.g.
            "Stirrup" or a project-specific shape name.

    Returns:
        DBS.RebarShape, or None.
    """
    name_lo = (name or u'').strip().lower()
    if not name_lo:
        return None
    for rs in DB.FilteredElementCollector(doc).OfClass(DBS.RebarShape).ToElements():
        try:
            if rs.Name.strip().lower() == name_lo:
                return rs
        except Exception:
            continue
    return None


def get_hook_type_by_angle(doc, angle_deg=90.0, tolerance_deg=1.0):
    """
    Find the project's RebarHookType whose HookAngle matches angle_deg
    (Phase 5, footing hooks/dowels).

    RebarHookType.HookAngle is in RADIANS, per the Revit API convention
    for angle-valued properties — converted here so this function works
    in degrees like the rest of this module's *_mm-at-the-boundary
    convention works in millimetres.

    Args:
        doc            (DB.Document)
        angle_deg      (float): target hook angle, degrees. 90 is the
                       standard "L-bar" anchorage hook this module's
                       footing dowels and hooked mat bars are written
                       for.
        tolerance_deg  (float): matching tolerance, degrees.

    Returns:
        DBS.RebarHookType, or None if no hook type is within tolerance.

    CALLER RESPONSIBILITY: a None return means "warn the user, don't
    create the hooked bars" — per this project's explicit rule, never
    pass None through to Rebar.CreateFromCurves's start_hook/end_hook
    silently and hope for a graceful Revit-side failure; check for None
    here first, where the message can name the missing hook angle.
    """
    target_rad = math.radians(angle_deg)
    tol_rad = math.radians(tolerance_deg)
    best, best_diff = None, 1e9

    for ht in DB.FilteredElementCollector(doc).OfClass(DBS.RebarHookType).ToElements():
        try:
            angle = ht.HookAngle
        except Exception:
            continue
        diff = abs(angle - target_rad)
        if diff < best_diff:
            best, best_diff = ht, diff

    return best if (best is not None and best_diff <= tol_rad) else None


def compute_vertical_hook_plane_normal(bar_direction, propagation_reference=None):
    """
    The correct `normal` argument for Rebar.CreateFromCurves when a
    STRAIGHT, HORIZONTAL bar (running along bar_direction, in a plan/XY
    plane) needs its ends to bend VERTICALLY (in Z) rather than
    horizontally in-plane (Phase 5.0's original bug) — whether that
    vertical bend is a short RebarHookType hook (dowels) or a full-depth
    U-bar leg drawn as explicit curve geometry (footing mats, Phase
    5.4's add_end_hooks()-based legs): the plane requirement is
    identical either way, only the leg/hook LENGTH differs.

    ROOT CAUSE THIS FIXES: `normal` in Rebar.CreateFromCurves defines
    the PLANE the whole shape — including its hooks — is considered to
    lie in; it is NOT the direction a hook bends toward. Passing a host
    face's normal (≈ ±Z for a horizontal mat, as Phase 5.0 did) tells
    Revit the shape's plane is roughly HORIZONTAL, so any hook on that
    shape bends WITHIN that horizontal plane — i.e. sideways, out of
    the concrete, exactly the failure this project observed. The
    correct plane for a horizontal bar with VERTICAL hooks is the
    VERTICAL plane containing both the bar's own direction and the
    global Z axis; this function returns that plane's normal.

    PHASE 5.6 — A SECOND BUG THIS FIXES (the propagation-direction SIGN):
    bar_direction x BasisZ has a FIXED rotational handedness — rotate
    bar_direction -90 degrees around Z. For a bar running along +X this
    gives -Y; for a bar running along +Y this gives +X. When this same
    normal also serves as a Rebar Set's PROPAGATION axis (see
    RebarWrapper.create_rebar_set and footing_rebar.build_mat_bar_set),
    two PERPENDICULAR bar directions that both need to propagate "into
    the footing" from their own starting edge can only have this fixed
    handedness match ONE of them — the other comes out backwards,
    sending that whole Set outside the footing (confirmed by Phase 5.5's
    live test: one mat direction correct, the other duplicated and
    floating outside). Passing `propagation_reference` — the direction
    the Set should actually end up moving toward — makes this function
    check the raw cross product's sign against it and flip if needed, so
    the result is correct for EITHER handedness case, not just the one
    the bare formula happens to favour.

    Args:
        bar_direction (DB.XYZ): the bar's own unit direction vector
            (e.g. (end_pt - start_pt).Normalize()).
        propagation_reference (DB.XYZ or None): if given, a vector
            pointing in the direction the result should generally agree
            with (e.g. from the bar's own position toward the mat's
            opposite edge) — the raw cross product is negated if its dot
            product with this reference is negative. Omit for the old,
            sign-unchecked behaviour (fine for a single hook/leg
            direction with no Set propagation involved, e.g. a use case
            that only needs SOME consistent vertical plane and doesn't
            care which of the two horizontal signs it gets).

    Returns:
        DB.XYZ: unit vector perpendicular to both bar_direction and
        DB.XYZ.BasisZ — i.e. horizontal, perpendicular to the bar's own
        run direction. This is the plane's normal (and, when
        propagation_reference is given, also the correctly-signed
        Set-propagation axis) — not a hook-BEND direction: which of the
        two ways a HOOK (not a Set) bends WITHIN this vertical plane (up
        vs down) is still governed by RebarHookOrientation (Left/Right)
        — see this module's API confidence notes for that separate,
        still-unverified question.

    NOTE — degenerate case: if bar_direction is itself parallel to
    global Z (a vertical bar, e.g. a column main bar or a footing
    dowel), the cross product is undefined (zero vector) — this
    function does not guard against that case, since every caller in
    this plugin so far (footing mat bars) only ever calls it with a
    HORIZONTAL bar_direction. A future vertical-bar caller needing
    horizontal hooks would need a different reference vector, not this
    function.
    """
    normal = bar_direction.CrossProduct(DB.XYZ.BasisZ).Normalize()
    if propagation_reference is not None and normal.DotProduct(propagation_reference) < 0:
        normal = normal.Multiply(-1.0)
    return normal


class RebarWrapper(object):
    """
    Thin, defensive wrapper around Rebar.CreateFromCurves and
    Rebar.CreateFromRebarShape.

    Every creation method:
      - opens its OWN Transaction — one Rebar element created = one undo
        step, matching this extension's established "one atomic user
        action per Transaction" convention (see the Fase 2 audit's
        TransactionGroup work for the multi-step-flow counterexample,
        which does not apply here: each Rebar creation call is already
        one atomic action on its own);
      - never raises on a Revit API failure — it catches the exception,
        records it on `self.last_error`, and returns None, so a caller
        driving a batch of many bars (e.g. one per
        split_rebar_by_stock_length segment) can just skip a None result
        and keep going instead of wrapping every single call in its own
        try/except.

    *** SEE THE MODULE DOCSTRING'S "API CONFIDENCE" SECTION ***
    Rebar.CreateFromCurves's parameter order below (RebarStyle,
    RebarBarType, start/end RebarHookType, host Element, normal XYZ,
    curves, start/end RebarHookOrientation, useExistingShapeIfPossible
    bool, createNewShape bool) is the Revit 2022+ documented signature,
    and the no-hook path (start_hook=end_hook=None) is now CONFIRMED
    against a live document (Phase 4). The start_hook/end_hook /
    *_hook_orientation parameters were already present in this method's
    signature from Phase 1 — Phase 5 is the first caller to actually
    pass non-None values for them (footing mat hooks and dowel anchors,
    both a single straight curve with a hook at one or both ends: pass
    a RebarHookType from get_hook_type_by_angle() as start_hook and/or
    end_hook, NOT pre-bent hook geometry in `curves` — Revit computes
    the hook's own geometry beyond the curve's endpoint from the
    RebarBarType, which is the whole point of using this parameter
    instead of drawing an L-shaped curve chain by hand). If Phase 5
    verification throws a TypeError here, this is where to look first.
    """

    def __init__(self, doc):
        self.doc = doc
        self.last_error = None

    def create_from_curves(self, host, curves, bar_type,
                            style=None, start_hook=None, end_hook=None,
                            normal=None,
                            start_hook_orientation=None,
                            end_hook_orientation=None,
                            use_existing_shape_if_possible=True,
                            create_new_shape=True,
                            transaction_name=u'NOSA — Create Rebar',
                            start_hook_direction=None, shape_name=None):
        """
        Create one Rebar element following an ordered list of curves —
        typically one RebarSegment.curve from
        split_rebar_by_stock_length() per call, one Rebar per commercial
        segment.

        Args:
            host    (DB.Element): the host structural element.
            curves  (list[DB.Curve]): ordered curve chain for this bar.
            bar_type (DBS.RebarBarType): from get_bar_type_by_diameter().
            style   (DBS.RebarStyle or None): defaults to
                RebarStyle.Standard (a normal reinforcing bar, not a
                stirrup/tie) if not given.
            start_hook / end_hook (DBS.RebarHookType or None): pass None
                for a bar with no hook at that end (the common case for
                straight, lap-spliced main bars).
            normal (DB.XYZ or None): the PLANE the shape (and any
                hooks) is considered to lie in — NOT the direction a
                hook bends toward, and NOT generally a host face's
                normal (that was Phase 5.0's bug — see
                compute_vertical_hook_plane_normal()'s docstring and
                this module's API confidence notes). For a straight,
                HORIZONTAL bar that needs VERTICAL hooks, pass
                compute_vertical_hook_plane_normal(bar_direction), not
                a face normal. Rebar.CreateFromCurves needs SOME normal
                even for a straight bar with no hooks at all.
            start_hook_orientation / end_hook_orientation
                (DBS.RebarHookOrientation or None): defaults to
                RebarHookOrientation.Left if not given.
            use_existing_shape_if_possible, create_new_shape (bool):
                passed straight through to Rebar.CreateFromCurves.
            transaction_name (unicode): Transaction display name.

        Returns:
            DBS.Rebar on success, or None on failure (see
            self.last_error for why).
        """
        from pyrevit import revit
        self.last_error = None

        if not curves:
            self.last_error = u'No curves supplied.'
            return None
        if bar_type is None:
            self.last_error = u'No RebarBarType supplied.'
            return None

        try:
            if style is None:
                style = DBS.RebarStyle.Standard
        except Exception as e:
            self.last_error = u'Could not resolve RebarStyle.Standard: {}'.format(e)
            return None

        try:
            default_orient = hook_orientation_left()
        except Exception:
            default_orient = None
        start_hook_orientation = start_hook_orientation or default_orient
        end_hook_orientation = end_hook_orientation or default_orient

        if normal is None:
            # Revit 2024+ rejects a null norm. Infer a plane normal from
            # the first curve (any unit vector perpendicular to it) —
            # a LAST-RESORT safety net for a caller that forgot to supply
            # its own normal; every typology module in this plugin
            # (footing/column/beam/wall) computes and passes its own
            # correct normal from real cross-section geometry, which
            # this generic fallback has no access to.
            try:
                c0 = curves[0]
                d = (c0.GetEndPoint(1) - c0.GetEndPoint(0)).Normalize()
                if abs(d.Z) < 0.95:
                    # Near-horizontal bar (beam/footing/wall bar) → plane
                    # is approximately horizontal, normal ≈ Z.
                    normal = DB.XYZ.BasisZ
                else:
                    # Near-vertical bar (column/dowel) needing a
                    # horizontal-plane normal: compute_vertical_hook_
                    # plane_normal(d) is explicitly documented as
                    # UNDEFINED here (bar_direction x BasisZ degenerates
                    # to a zero vector as d approaches pure vertical —
                    # exactly this branch's whole input range). A generic
                    # fallback with no cross-section context cannot pick
                    # the column's real face direction anyway, so use a
                    # fixed, always-well-defined horizontal reference
                    # instead of a formula that blows up on its own input.
                    normal = DB.XYZ.BasisX
                if normal is None or normal.GetLength() < 1e-9:
                    normal = DB.XYZ.BasisZ
            except Exception as e:
                self.last_error = u'Could not infer rebar plane normal: {}'.format(e)
                return None

        curve_list = List[DB.Curve](curves)
        self.shape_warning = None

        try:
            with revit.Transaction(transaction_name):
                if shape_name and start_hook is None and end_hook is None:
                    rebar = _create_rebar(self, style, bar_type, host, normal, curve_list,
                                          shape_name)
                else:
                    rebar = rebar_from_curves(
                        self.doc, style, bar_type, start_hook, end_hook,
                        host, normal, curve_list,
                        start_hook_orientation, end_hook_orientation,
                        use_existing_shape_if_possible, create_new_shape)
                # BUG FIX (2026-09-01) — CreateFromCurves can reject a
                # shape by returning None WITHOUT raising, which this
                # branch never checked: self.last_error was left at its
                # initial None, so every caller's own error message
                # rendered the literal text "— None" (reported live for
                # footing/floor perimeter closure U-bars — a genuine
                # Rebar.CreateFromCurves rejection with zero diagnostic
                # information, previously indistinguishable from "no
                # error occurred"). create_rebar_set already had this
                # exact check; create_from_curves did not.
                if rebar is None:
                    self.last_error = u'Rebar.CreateFromCurves returned None.'
                else:
                    realign_closed_loop(self.doc, rebar, curves)
                    if start_hook is not None and start_hook_direction is not None:
                        point_start_hook(self.doc, rebar, start_hook_direction)
            return rebar
        except Exception as e:
            self.last_error = u'Rebar.CreateFromCurves failed: {}'.format(e)
            return None

    def create_lapped_circle_set(self, host, bar_type, centre, radius_mm, lap_mm,
                                 spacing_mm, array_length_mm,
                                 transaction_name=u'NOSA — Create Circular Links'):
        """
        A Rebar Set of closed lapped circular links (shape 75): centreline
        radius radius_mm around `centre`, laps lap_mm, spaced along +Z.
        Revit rejects a circle built from curves, so the project's own
        LappedCircle shape is placed, sized (A = outer diameter, B = lap)
        and moved onto the centre (T2.20, user decision 2026-09-30).
        Returns the Rebar, or None (see last_error) so the caller can fall
        back to the polygon link.
        """
        from pyrevit import revit
        self.last_error = None
        shape = find_lapped_circle_shape(self.doc)
        if shape is None:
            self.last_error = u'No lapped circular link RebarShape (75) is loaded in this project.'
            return None
        try:
            with revit.Transaction(transaction_name):
                rebar = DBS.Rebar.CreateFromRebarShape(
                    self.doc, shape, bar_type, host, centre, DB.XYZ.BasisX, DB.XYZ.BasisY)
                if rebar is None:
                    self.last_error = u'Rebar.CreateFromRebarShape returned None.'
                    return None
                bar_dia_ft = bar_type.BarModelDiameter
                rebar.LookupParameter(u'A').Set(2.0 * radius_mm / _MM_PER_FT + bar_dia_ft)
                rebar.LookupParameter(u'B').Set(lap_mm / _MM_PER_FT)
                self.doc.Regenerate()
                arcs = [crv for crv in rebar.GetTransformedCenterlineCurves(
                    False, False, False, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0)
                    if isinstance(crv, DB.Arc)]
                if arcs:
                    DB.ElementTransformUtils.MoveElement(self.doc, rebar.Id, centre - arcs[0].Center)
                try:
                    rebar.GetShapeDrivenAccessor().SetLayoutAsMaximumSpacing(
                        spacing_mm / _MM_PER_FT, array_length_mm / _MM_PER_FT, True, True, True)
                except Exception as e:
                    self.last_error = (u'Circular link created as a single bar, but Rebar Set '
                                       u'propagation failed: {}'.format(e))
            return rebar
        except Exception as e:
            self.last_error = u'Circular link (shape 75) failed: {}'.format(e)
            return None

    def create_rebar_set(self, host, curves, bar_type, spacing_mm, array_length_mm,
                          normal=None, style=None,
                          bars_on_normal_side=True, include_first_bar=True, include_last_bar=True,
                          transaction_name=u'NOSA — Create Rebar Set'):
        """
        Create ONE Rebar from `curves` (a single shape) and immediately
        propagate it into a Rebar SET via its ShapeDrivenAccessor — ONE
        Revit element represents the whole row/perimeter of bars
        (critical for performance and for schedules/quantities to count
        it as a set with a bar-count property), instead of this
        engine's caller looping over N separate create_from_curves
        calls.

        *** OPEN-SHAPE HISTORY — READ BEFORE CHANGING `normal` HERE ***
        Phase 5.1 tried this call with an OPEN, hook-bearing multi-curve
        chain (a footing mat's [hook, line, hook] bar) and it failed
        outright — no Rebar created at all. It DID succeed, in that same
        round of testing, for a CLOSED rectangular loop
        (footing_rebar.build_side_rebar_set's perimeter). At the time
        this was attributed to "no fillet between orthogonal segments in
        an open shape," and footing mat bars moved to plain
        create_from_curves in a loop (footing_rebar.build_mat_bar_chains,
        Phase 5.2/5.4) to avoid the open-shape Set path entirely.

        Phase 5.5 retries the open-shape Set (footing_rebar.
        build_mat_bar_set) on a different theory: Phase 5.1 ALSO passed
        the WRONG `normal` for that shape (a host face's, ≈ vertical Z,
        for bars that needed a HORIZONTAL plane) — since both the
        shape's plane AND this method's Set-propagation axis derive from
        `normal`, a wrong value may have been sufficient on its own to
        make Revit reject the shape, independent of the fillet/corner
        question. If mats STILL fail as a Set even with the corrected
        normal (rebar_engine.compute_vertical_hook_plane_normal), THEN
        the fillet/corner-radius theory becomes the leading suspect
        again — footing_rebar.build_mat_bar_chains remains available,
        fully working, as the fallback either way.

        Deliberately takes NO start_hook/end_hook/orientation
        parameters (unlike create_from_curves above) — any hook
        geometry must be baked directly into `curves` instead. If a
        future caller genuinely needs a RebarHookType-driven SET, that
        would need a new parameter here, not an argument to reuse — it
        doesn't exist yet (and, per the paragraph above, may not work
        for an open shape anyway).

        *** THE LOWEST-CONFIDENCE CALL IN THIS ENGINE — READ THIS ***
        Rebar.GetShapeDrivenAccessor() and
        ShapeDrivenAccessor.SetLayoutAsMaximumSpacing(spacing,
        arrayLength, barsOnNormalSide, includeFirstBar, includeLastBar)
        are real, documented Revit Structure API members, but this
        exact parameter order has NOT been exercised against a live
        document — Phase 4/5 only confirmed plain create_from_curves.
        The accessor call is wrapped in its OWN try/except, nested
        inside the Transaction: if it fails, the single Rebar already
        created by CreateFromCurves is left in the model AS A SINGLE
        BAR (not rolled back) and self.last_error explains that the SET
        propagation specifically failed — a partial success, not a
        silently lost Transaction. Check self.last_error even when this
        method returns a Rebar, to tell a full success from a
        "created as one bar, not propagated" partial one.

        Args:
            host                 (DB.Element): the host structural element.
            curves               (list[DB.Curve]): the set's initial/only
                                 shape.
            bar_type             (DBS.RebarBarType)
            spacing_mm           (float): MAXIMUM spacing between bar
                                 positions in the set, mm.
            array_length_mm      (float): total distance the set spans,
                                 mm — e.g. a mat's usable width in the
                                 propagation direction
                                 (build_mat_bar_set's 'array_length_mm'),
                                 or the vertical gap between a footing's
                                 bottom and top cover elevations for side
                                 rebar (build_side_rebar_set's).
            normal               (DB.XYZ or None): reference plane normal,
                                 same meaning as create_from_curves's.
            style                (DBS.RebarStyle or None): defaults to
                                 RebarStyle.Standard — pass
                                 RebarStyle.StirrupTie for a CLOSED loop
                                 shape (e.g. side rebar's perimeter
                                 rectangle), which is the Revit-side
                                 distinction between an open bar and a
                                 closed tie/stirrup shape.
            bars_on_normal_side, include_first_bar, include_last_bar
                                 (bool): passed to
                                 SetLayoutAsMaximumSpacing — the defaults
                                 (True, True, True) put a bar at BOTH
                                 ends of array_length_mm and fill evenly
                                 between at <= spacing_mm, matching this
                                 engine's established even-distribution
                                 philosophy (see
                                 split_rebar_by_stock_length).
            transaction_name     (unicode): Transaction display name.

        Returns:
            DBS.Rebar on success (whether or not the SET propagation
            itself succeeded — see self.last_error), or None if even the
            initial Rebar.CreateFromCurves failed.
        """
        from pyrevit import revit
        self.last_error = None

        if not curves:
            self.last_error = u'No curves supplied.'
            return None
        if bar_type is None:
            self.last_error = u'No RebarBarType supplied.'
            return None

        try:
            if style is None:
                style = DBS.RebarStyle.Standard
        except Exception as e:
            self.last_error = u'Could not resolve RebarStyle.Standard: {}'.format(e)
            return None

        curve_list = List[DB.Curve](curves)
        spacing_ft = spacing_mm / _MM_PER_FT
        array_length_ft = array_length_mm / _MM_PER_FT

        try:
            with revit.Transaction(transaction_name):
                rebar = rebar_from_curves(
                    self.doc, style, bar_type, None, None,
                    host, normal, curve_list,
                    hook_orientation_left(), hook_orientation_left(),
                    True, True)
                if rebar is None:
                    self.last_error = u'Rebar.CreateFromCurves returned None.'
                    return None
                try:
                    accessor = rebar.GetShapeDrivenAccessor()
                    accessor.SetLayoutAsMaximumSpacing(
                        spacing_ft, array_length_ft, bars_on_normal_side,
                        include_first_bar, include_last_bar)
                except Exception as e:
                    self.last_error = (u'Rebar created as a single bar, but Rebar Set '
                                        u'propagation failed: {}'.format(e))
                realign_closed_loop(self.doc, rebar, curves)
            return rebar
        except Exception as e:
            self.last_error = u'Rebar.CreateFromCurves failed: {}'.format(e)
            return None

    def create_rebar_set_fixed_number(self, host, curves, bar_type, count, array_length_mm,
                                       normal=None, style=None,
                                       bars_on_normal_side=True, include_first_bar=True,
                                       include_last_bar=True,
                                       transaction_name=u'NOSA — Create Rebar Set',
                                       shape_name=None):
        """
        PHASE 3.2 — sibling of create_rebar_set, for a Set whose bar
        COUNT is the fixed, known quantity (e.g. a column face's own
        n_u/n_v perimeter bar count) rather than a maximum spacing to
        fill an array_length with as many bars as fit. Same structure,
        same partial-failure contract (see create_rebar_set's own
        docstring — everything there about the Transaction, the
        "created as Single, propagation failed" partial-success case,
        and the confidence caveat on
        Rebar.GetShapeDrivenAccessor()/the ShapeDrivenAccessor API
        applies here identically), the only difference being the
        underlying accessor call:
        ShapeDrivenAccessor.SetLayoutAsFixedNumber(numberOfBarPositions,
        arrayLength, barsOnNormalSide, includeFirstBar, includeLastBar)
        instead of SetLayoutAsMaximumSpacing.

        Args:
            host, curves, bar_type, normal, style, transaction_name:
                          same meaning as create_rebar_set.
            count         (int): exact number of bar positions in the
                          set (Revit's own "numberOfBarPositions").
            array_length_mm (float): distance spanned by the set, mm —
                          e.g. one column face's own edge length between
                          its two end bars.
            bars_on_normal_side, include_first_bar, include_last_bar
                          (bool): passed to SetLayoutAsFixedNumber —
                          see create_rebar_set's own docstring for the
                          same parameters' meaning.

        Returns:
            DBS.Rebar on success (whether or not the SET propagation
            itself succeeded — see self.last_error), or None if even the
            initial Rebar.CreateFromCurves failed.
        """
        from pyrevit import revit
        self.last_error = None

        if not curves:
            self.last_error = u'No curves supplied.'
            return None
        if bar_type is None:
            self.last_error = u'No RebarBarType supplied.'
            return None
        if count is None or count < 1:
            self.last_error = u'count must be at least 1.'
            return None

        try:
            if style is None:
                style = DBS.RebarStyle.Standard
        except Exception as e:
            self.last_error = u'Could not resolve RebarStyle.Standard: {}'.format(e)
            return None

        curve_list = List[DB.Curve](curves)
        array_length_ft = array_length_mm / _MM_PER_FT
        self.shape_warning = None

        try:
            with revit.Transaction(transaction_name):
                rebar = _create_rebar(self, style, bar_type, host, normal, curve_list, shape_name)
                if rebar is None:
                    self.last_error = u'Rebar.CreateFromCurves returned None.'
                    return None
                try:
                    accessor = rebar.GetShapeDrivenAccessor()
                    accessor.SetLayoutAsFixedNumber(
                        int(count), array_length_ft, bars_on_normal_side,
                        include_first_bar, include_last_bar)
                except Exception as e:
                    self.last_error = (u'Rebar created as a single bar, but Rebar Set '
                                        u'propagation failed: {}'.format(e))
                realign_closed_loop(self.doc, rebar, curves)
            return rebar
        except Exception as e:
            self.last_error = u'Rebar.CreateFromCurves failed: {}'.format(e)
            return None

    def create_freeform_group(self, host, curve_groups, bar_type,
                               transaction_name=u'NOSA — Create FreeForm Rebar Group'):
        """
        PHASE 2.4 (signature corrected in Phase 2.5 from a live error) —
        groups several DISTINCT, independently-shaped bar curve chains
        (e.g. one per irregular scanline row near a chamfered edge,
        each a different length — exactly what a Rebar Set cannot
        represent, since a Set only repeats ONE identical shape at even
        spacing) into ONE Rebar element, via Rebar.CreateFreeForm(
        Document, RebarBarType, Element, IList<CurveLoop>, out
        RebarFreeFormValidationResult).

        PHASE 2.5 FIX — the actual .NET signature, confirmed by a live
        TypeError ("expected IList[CurveLoop], got List[List[Curve]]"):
        Phase 2.4 guessed an IList<IList<Curve>> overload from written
        API documentation; the live Revit session rejected it —
        IronPython does not implicitly convert a nested Python list of
        lists into .NET generic collections, and the real overload
        takes ONE CurveLoop per bar (not a plain curve list). Each
        curve_groups[i] is now wrapped into its own DB.CurveLoop() via
        repeated .Append(curve) calls (a CurveLoop here is just an
        ordered, explicitly-constructed CHAIN of curves — it does not
        need to be closed), and those loops are collected into a
        List[DB.CurveLoop]() via .Add(), not the List[T](iterable)
        constructor-from-Python-list form Phase 2.4 used — building the
        .NET collection through its own native methods end-to-end
        avoids relying on IronPython to guess the right coercion for a
        nested structure again.

        CONFIDENCE: MEDIUM — the overload and CurveLoop.Append usage
        are now corroborated by a live Revit TypeError (not just
        written docs) telling us the exact expected type; the
        constructor pattern itself has not yet round-tripped a
        successful live creation in this project. Free Form Rebar
        created this way is UNCONSTRAINED — no cover/host constraint
        can be added to it afterward, only its already-baked-in
        geometry, which is fine here since every curve this project
        passes in already has real cover applied. If this call still
        fails for any reason, this method returns None with
        self.last_error explaining why — the CALLER MUST fall back to
        individual create_from_curves bars, one per curve group.

        *** "SHAPE 00" IS INHERENT TO THIS METHOD, AND IS ACCEPTED ***
        Live testing found every Rebar created this way reports
        RebarShapeId "00" (generic/unnamed) in Revit, even for curve
        groups that are individually clean, orthogonal U-bars. This is
        NOT a geometry-precision defect fixable by adjusting bend
        radius or coordinate rounding: Rebar.CreateFreeForm bypasses
        Revit's RebarShapeMatch machinery entirely — a Free Form Rebar
        has no RebarShape association at all in Revit's own data model
        (there is no post-creation "assign/force a shape" API to call;
        RebarShapeId is simply absent for this creation path, by
        design, not a value this wrapper — or any caller — can set).
        Shape matching (Shape 21 for a U-bar, etc.) only ever happens
        inside Rebar.CreateFromCurves's own useExistingShapeIfPossible/
        createNewShape logic.

        PHASE 3.5 DECISION (explicit, overriding an earlier reversal of
        this same call): this project's floor module DELIBERATELY calls
        this method for its irregular perimeter/main-grid remainder
        (chamfer and hole-transition rows a Rebar Set cannot represent)
        rather than looping create_from_curves per row — trading away
        the Shape 21/01 name for ONE MRA-taggable, schedulable Rebar
        element instead of hundreds of anonymous loose bars. A generic
        Shape 00 has no drawing-side consequence Revit enforces; an
        un-groupable bar count that breaks Multi-Rebar Annotation and
        schedules does. Do not "fix" this call site back to
        create_from_curves again without the user's explicit sign-off —
        this exact trade-off has been requested twice.

        Args:
            host         (DB.Element)
            curve_groups (list[list[DB.Curve]]): one curve chain per
                         bar shape to bundle into this ONE Rebar
                         element — the group members do NOT need to be
                         identical or evenly spaced.
            bar_type     (DBS.RebarBarType)
            transaction_name (unicode)

        Returns:
            DBS.Rebar on success, or None (see self.last_error).
        """
        from pyrevit import revit
        self.last_error = None

        if not curve_groups:
            self.last_error = u'No curve groups supplied.'
            return None
        if bar_type is None:
            self.last_error = u'No RebarBarType supplied.'
            return None

        try:
            loop_list = List[DB.CurveLoop]()
            for chain in curve_groups:
                loop = DB.CurveLoop()
                for curve in chain:
                    loop.Append(curve)
                loop_list.Add(loop)
        except Exception as e:
            self.last_error = u'Could not build the IList<CurveLoop> argument: {}'.format(e)
            return None

        try:
            with revit.Transaction(transaction_name):
                result = DBS.Rebar.CreateFreeForm(self.doc, bar_type, host, loop_list)
                if isinstance(result, tuple):
                    rebar, validation = result[0], result[1]
                else:
                    rebar, validation = result, None
                if rebar is not None and all(len(chain) > 1 for chain in curve_groups):
                    set_workshop_bent(rebar)
            if rebar is None:
                self.last_error = u'Rebar.CreateFreeForm returned None (validation: {}).'.format(validation)
                return None
            try:
                if validation is not None and validation != DBS.RebarFreeFormValidationResult.Success:
                    self.last_error = u'Rebar.CreateFreeForm validation reported: {}'.format(validation)
            except Exception:
                pass
            return rebar
        except Exception as e:
            self.last_error = u'Rebar.CreateFreeForm failed: {}'.format(e)
            return None

    def create_from_shape(self, host, rebar_shape, bar_type,
                           origin, x_vec, y_vec,
                           transaction_name=u'NOSA — Create Rebar from Shape'):
        """
        Create one Rebar element from a predefined RebarShape (e.g. a
        stirrup/tie shape), positioned by an origin point and two
        orthogonal direction vectors that define the shape's local
        X/Y axes in model space.

        Args:
            host        (DB.Element): the host structural element.
            rebar_shape (DBS.RebarShape): from get_rebar_shape_by_name().
            bar_type    (DBS.RebarBarType): from get_bar_type_by_diameter().
            origin      (DB.XYZ): shape placement origin.
            x_vec, y_vec (DB.XYZ): the shape's local axes, orthogonal
                unit vectors.
            transaction_name (unicode): Transaction display name.

        Returns:
            DBS.Rebar on success, or None on failure (see
            self.last_error for why).
        """
        from pyrevit import revit
        self.last_error = None

        if rebar_shape is None:
            self.last_error = u'No RebarShape supplied.'
            return None
        if bar_type is None:
            self.last_error = u'No RebarBarType supplied.'
            return None

        try:
            with revit.Transaction(transaction_name):
                rebar = DBS.Rebar.CreateFromRebarShape(
                    self.doc, rebar_shape, bar_type, host, origin, x_vec, y_vec)
            return rebar
        except Exception as e:
            self.last_error = u'Rebar.CreateFromRebarShape failed: {}'.format(e)
            return None


# ══════════════════════════════════════════════════════════════════════════
# SECTION 3 — Stock-length splitting & lap engine (the critical core)
# ══════════════════════════════════════════════════════════════════════════

class RebarSegment(object):
    """
    One commercial-length piece resulting from
    split_rebar_by_stock_length().

    Attributes:
        index          (int): 0-based position along the original bar,
                       from the curve's start to its end.
        curve          (DB.Curve): final geometry for this piece — a
                       Line, transversely offset from the ideal
                       centerline if it participates in a lap splice, so
                       two adjacent lapped bars don't sit on the exact
                       same line in the 3D model (see
                       split_rebar_by_stock_length's docstring for the
                       offset pattern). Ready to pass straight into
                       RebarWrapper.create_from_curves([curve], ...).
        length_mm      (float): this segment's length along the bar
                       axis (identical to the offset curve's own length,
                       since the offset is a pure translation).
        has_start_lap  (bool): True if this segment overlaps the
                       previous one in a lap splice at its start.
        has_end_lap    (bool): True if this segment overlaps the next
                       one in a lap splice at its end.
    """
    def __init__(self, index, curve, length_mm, has_start_lap, has_end_lap):
        self.index = index
        self.curve = curve
        self.length_mm = length_mm
        self.has_start_lap = has_start_lap
        self.has_end_lap = has_end_lap


def _stable_perpendicular(direction):
    """
    A unit vector perpendicular to `direction`, stable for any
    direction including near-vertical bars (falls back to a different
    reference axis rather than letting the cross product degenerate
    toward zero). Same technique as SiteToolkit's _plane_for_line — kept
    as a private duplicate here rather than a shared import, since the
    two modules are for unrelated plugins and this keeps rebar_engine.py
    self-contained for whoever picks up Phase 2.
    """
    up = DB.XYZ.BasisZ
    if abs(direction.DotProduct(up)) > 0.999:
        up = DB.XYZ.BasisX
    return direction.CrossProduct(up).Normalize()


def split_rebar_by_stock_length(curve, stock_length_mm, lap_length_mm,
                                 lap_offset_mm=25.0, first_length_mm=None):
    """
    Split an idealised, over-length rebar curve into commercial-length
    segments with normative lap splices, transversely offsetting
    adjacent lapped segments so they don't physically coincide in the
    3D model.

    ALGORITHM
    ---------
    1. If the bar already fits within one stock length, return it
       unmodified as a single segment — no split, no offset.
    2. Otherwise, compute how many segments are needed so that every
       pair of consecutive segments overlaps by AT LEAST lap_length_mm:
       each additional segment beyond the first only needs to cover
       (stock_length - lap_length) of NEW length, so
           n_segments = ceil((total_length - stock_length)
                              / (stock_length - lap_length)) + 1
    3. BUG FIX (2026-09-01, superseded by the GREEDY fix below) — every
       segment used to be given the SAME (shorter, <= stock_length)
       length, chosen so consecutive segments overlap by EXACTLY
       lap_length_mm — this fixed the far worse original bug (a 4m
       overlap on a 12m bar split at 8m stock with a ~480mm intended
       lap), but distributed the SHORTFALL evenly across every segment,
       producing N non-standard bar lengths for the schedule instead of
       N-1 full stock bars + one short remainder.
    3'. GREEDY FIX (2026-09-01, per explicit user preference) — every
       segment except the LAST is now exactly stock_length_mm long
       (the maximum allowed); only the final segment is shorter,
       absorbing whatever remains:
           advance    = stock_length - lap_length        (fixed step)
           segment[i].start = i * advance                for i < n-1
           segment[i].end   = segment[i].start + stock_length
           segment[n-1].start = (n-1) * advance
           segment[n-1].end   = total_length              (remainder)
       This is the SAME n_segments as step 2 (that formula already IS
       the greedy step size) — algebraically guaranteed: the last
       segment's own length (total_length - (n-1)*advance) is > 0 and
       <= stock_length by the minimality of n_segments (see the
       derivation kept in the implementation below), and every
       consecutive pair still overlaps by EXACTLY lap_length_mm (full-
       stock segments step by `advance` = stock-lap; the last segment's
       own start is placed the same way). Fewer distinct bar lengths on
       the BBS, at the cost of one asymmetric "remainder" bar instead of
       N equal ones — a deliberate fabrication-friendliness trade the
       user asked for explicitly over the previous even split.
    4. For each segment, extract its Line and — if it has a lap at
       either end — shift it transversely by +-lap_offset_mm/2,
       alternating direction by segment index (even segments shift one
       way, odd segments the other). Every pair of ADJACENT segments
       therefore differs by the full lap_offset_mm at their shared lap
       zone (avoiding a literal 3D coincidence there), while the
       average path stays centred on the original curve rather than
       drifting to one side.

    SCOPE
    -----
    Exact for straight bars (a DB.Line curve) — the primary case this
    function exists for (long vertical column/wall main bars exceeding
    the ~12 m commercial stock length). A non-Line Curve is still
    accepted: point-at-distance is approximated via
    Curve.Evaluate(normalizedParam, True), which is only exactly
    arc-length-uniform for a Line — for a curved bar, actual segment
    lengths will drift slightly from the target stock length. The
    transverse lap-offset is SKIPPED entirely for non-Line input (a
    single "perpendicular" direction is not well-defined for a curve
    whose local direction varies along its length) — segments still get
    created and still lap correctly in terms of geometry, they just
    won't be transversely separated, so collision avoidance for curved
    bars is a documented gap, not a silent one.

    Args:
        curve            (DB.Curve): the ideal, full-length bar geometry.
        stock_length_mm  (float): max commercial bar length, e.g. 12000
                          for a standard 12 m stock bar.
        lap_length_mm    (float): normative lap splice length, already
                          computed by the caller (e.g. per EC2 anchorage
                          / lap length rules, or a BS 8666 table) — this
                          function does not calculate code-compliance
                          lap lengths itself, only applies a given one.
        lap_offset_mm    (float): transverse separation applied between
                          two lapped segments, default 25mm. Override
                          with something diameter-derived (e.g. 1-2x bar
                          diameter) once a real bar diameter is known —
                          25mm is a reasonable flat default, not a
                          normative value.

    Returns:
        list[RebarSegment], ordered from the curve's start to its end.

    Raises:
        ValueError: if stock_length_mm <= 0, lap_length_mm < 0, or
        lap_length_mm >= stock_length_mm (a lap can't be as long as or
        longer than the stock piece it's splicing — degenerate input
        that would otherwise divide by zero / loop forever below).
    """
    if stock_length_mm <= 0:
        raise ValueError(u'stock_length_mm must be > 0.')
    if lap_length_mm < 0:
        raise ValueError(u'lap_length_mm must be >= 0.')
    if lap_length_mm >= stock_length_mm:
        raise ValueError(u'lap_length_mm must be smaller than stock_length_mm.')

    total_length_ft = curve.Length
    stock_ft = stock_length_mm / _MM_PER_FT
    lap_ft = lap_length_mm / _MM_PER_FT
    offset_ft = lap_offset_mm / _MM_PER_FT

    # Case 1: no split needed — return the original curve untouched.
    if total_length_ft <= stock_ft + 1e-6:
        return [RebarSegment(0, curve, total_length_ft * _MM_PER_FT, False, False)]

    advance = stock_ft - lap_ft
    # Staggered laps (T4.8): a shorter first piece moves every lap of this bar along.
    first_ft = stock_ft
    if first_length_mm is not None and lap_ft < first_length_mm / _MM_PER_FT < stock_ft:
        first_ft = first_length_mm / _MM_PER_FT
    if total_length_ft <= first_ft + 1e-6:
        first_ft = stock_ft
    n_segments = int(math.ceil(max(0.0, total_length_ft - first_ft) / advance - 1e-9)) + 1
    # GREEDY FIX (2026-09-01, per explicit user preference over the
    # previous equal-length distribution) — every segment except the
    # last is exactly stock_ft long (the maximum); the last absorbs the
    # remainder. Correctness of "the last segment's own length lands in
    # (0, stock_ft]" follows directly from n_segments' own minimality:
    # let k = n_segments - 1. By definition of ceil, k is the SMALLEST
    # integer with k*advance >= total_length_ft - stock_ft, i.e.
    #   total_length_ft - k*advance <= stock_ft         (last seg fits)
    # and (k-1) does NOT satisfy that inequality (whenever k >= 1), i.e.
    #   (k-1)*advance < total_length_ft - stock_ft
    #   k*advance      < total_length_ft - stock_ft + advance
    #                  = total_length_ft - lap_ft
    #   total_length_ft - k*advance > lap_ft > 0          (last seg > 0)
    # so the last segment's length is guaranteed in (lap_ft, stock_ft].
    # Every consecutive pair (including the last) still overlaps by
    # EXACTLY lap_ft: full-stock segments start advance_ft apart by
    # construction, and the last segment's own start is placed the same
    # advance_ft after the second-to-last segment's start.

    is_line = isinstance(curve, DB.Line)
    direction = None
    perp = None
    origin = None
    if is_line:
        origin = curve.GetEndPoint(0)
        direction = curve.Direction
        perp = _stable_perpendicular(direction)

    def _point_at(dist_ft):
        if is_line:
            return origin + direction.Multiply(dist_ft)
        # Approximation for non-Line curves — see docstring's SCOPE note.
        t = dist_ft / total_length_ft
        t = min(max(t, 0.0), 1.0)
        return curve.Evaluate(t, True)

    segments = []
    for i in range(n_segments):
        start_ft = 0.0 if i == 0 else (first_ft - lap_ft) + (i - 1) * advance
        end_ft = total_length_ft if i == n_segments - 1 else start_ft + (first_ft if i == 0 else stock_ft)
        p0 = _point_at(start_ft)
        p1 = _point_at(end_ft)

        has_start_lap = i > 0
        has_end_lap = i < n_segments - 1

        if perp is not None and (has_start_lap or has_end_lap):
            side = -1.0 if i % 2 == 0 else 1.0
            shift = perp.Multiply(side * offset_ft / 2.0)
            p0 = p0 + shift
            p1 = p1 + shift

        seg_curve = DB.Line.CreateBound(p0, p1)
        length_mm = (end_ft - start_ft) * _MM_PER_FT
        segments.append(RebarSegment(i, seg_curve, length_mm, has_start_lap, has_end_lap))

    return segments
