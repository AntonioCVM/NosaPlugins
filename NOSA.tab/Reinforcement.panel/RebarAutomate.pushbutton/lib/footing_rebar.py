# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Footing Rebar (Phase 2)
============================================================================

Category module for isolated and strip footings. Loads rebar_engine.py
in isolation via nosa_utils.bootstrap.load_module (unique alias
're_engine'), matching this extension's established sys.modules
isolation convention.

Pure geometry/math — NO UI, no direct Rebar.CreateFromCurves calls of
its own. Every public function here returns DB.Curve objects (or lists
of them) that a caller hands to rebar_engine.RebarWrapper for actual
element creation; this module never opens a Transaction itself.

SCOPE
-----
Targets the common case: a footing whose bottom (and, for Phase 5's top
mat, top) face is a single planar face (true for both isolated pad
footings and straight-run strip footings). A footing with a sloped or
stepped top/underside would need a different, non-planar approach this
module does not attempt — see get_footing_bottom_face() /
get_footing_top_face()'s docstrings.

The anchorage-length helper (default_anchorage_length_mm) is a simple
bar-diameter multiple, NOT a full EC2 bond-stress calculation (that
needs concrete class, bond condition, and bar-type coefficients this
module has no access to) — see its own docstring for why, and what a
caller doing real code-compliance work should do instead.

PHASE 5.1 — REBAR SETS, AND HOOKS ARE BACK TO EXPLICIT GEOMETRY
------------------------------------------------------------------
Phase 5 tried RebarHookType-driven hooks (Rebar.CreateFromCurves's
start_hook/end_hook + RebarHookOrientation), reasoning that Revit
computing the hook geometry itself would be more accurate than hand-
drawn stubs. Live testing proved this wrong in practice: the hook bent
in the HORIZONTAL plane (out of the concrete) instead of vertically
(into it) — the RebarHookOrientation.Left/Right guess disclosed in
Phase 5's docstring turned out not to control the plane the way
expected. Rather than keep guessing combinations against a live model,
Phase 5.1 reverts to explicit geometry for MAT hooks specifically:
each hooked bar is now a 3-curve chain — [vertical hook, horizontal
main bar, vertical hook] — built by add_end_hooks() bending toward
-face_info.normal (i.e. always "into the concrete", correct for both
the bottom mat, whose normal points down, and the top mat, whose
normal points up, without any conditional). This makes the Z-plane
correct by CONSTRUCTION, not by hoping an enum member does the right
thing — see build_mat_bar_chains()'s docstring (Phase 5.2 renamed this
function, see below, but kept the hook-geometry fix). add_end_hooks()
itself (Phase 2) is unchanged; Phase 5.1 is simply the first caller to
route through it again after Phase 5's detour.

Dowels are UNCHANGED from Phase 5 and still use RebarHookType — this
message's brief scoped the hook-geometry fix to mat bars specifically
("en las mallas"), and dowel hooks were not reported broken.

Phase 5.1 also introduced build_mat_bar_set() / build_side_rebar_set()
returning ONE representative bar shape plus an `array_length_mm` /
`spacing_mm` pair instead of a pre-computed list of N individual bars —
the caller (rebar_engine.RebarWrapper.create_rebar_set) creates ONE
Rebar element and propagates it into a Rebar Set via
ShapeDrivenAccessor.SetLayoutAsMaximumSpacing, matching how an
engineer actually works in Revit's own UI (draw one bar, then set its
layout) and — per the brief — critical for schedule/quantity take-off,
which counts a Rebar Set as one countable item with a bar-count
property, not N separate elements.

PHASE 5.2 — SETS REVERTED FOR MATS (SIDE REBAR KEEPS ITS SET, FIXED)
------------------------------------------------------------------
Live testing of Phase 5.1 surfaced two bugs:

  BUG 1 (mats not created at all): Rebar.GetShapeDrivenAccessor()
  .SetLayoutAsMaximumSpacing failed for the mats' OPEN, hook-bearing
  3-curve [hook, line, hook] shape — most likely because Revit could
  not auto-derive a valid RebarShape from that curve topology in the
  test model (the closed-loop side-rebar shape, by contrast, DID work
  as a Set — see BUG 2). Rather than keep debugging shape auto-
  detection blind, Phase 5.2 reverts MAT bars to Phase 5.0's per-bar
  LOOP: build_mat_bar_chains() (replacing build_mat_bar_set() as the
  function build_footing_reinforcement() below calls) returns a LIST
  of individual bar chains per direction again, and the caller
  (ui.py) creates one Rebar per chain via
  RebarWrapper.create_from_curves — "20 individual bars, correctly
  modelled" over "0 bars", per the brief. The Phase 5.1 hook-geometry
  fix itself (bending toward -face_info.normal, forcing the vertical
  plane by construction) is UNCHANGED and still applied per bar.

  BUG 2 (side rebar positioned below/outside the footing): the Rebar
  Set mechanism itself worked for side rebar's closed rectangle, but
  build_side_rebar_set()'s Z coordinates were wrong — derived from
  bottom_face.origin.Z / top_face's face-normal arithmetic, which
  depends on get_host_solid()/get_footing_top_face() having picked
  exactly the right face for elevation purposes. Fixed to read
  host.get_BoundingBox(None) directly (the element's own global,
  axis-aligned bounding box) for Zmin/Zmax — the same simpler, already-
  global API create_rebar_detail_section already uses successfully —
  and to pass DB.XYZ.BasisZ (straight up) as the Set's reference
  `normal` instead of bottom_face.normal (which points down), on the
  reasoning that ShapeDrivenAccessor propagates along +normal and a
  downward normal may have been sending the propagated copies further
  DOWN from the first (correctly placed) loop instead of up toward the
  top mat. CONFIRMED CORRECT by live testing: side rebar now generates
  "absolutamente perfecta en coordenadas y propagación."

PHASE 5.3 — THE ACTUAL ROOT CAUSE OF THE HORIZONTAL-HOOK BUG
------------------------------------------------------------------
Phase 5.2's mat bars still failed to create at all — this time because
Rebar.CreateFromCurves itself rejected the [hook, line, hook] 3-curve
chain (most likely: no fillet between the orthogonal hook/main-bar
segments, which the RebarBarType's own bend-radius rules don't allow
Revit to auto-fit a RebarShape to). So mats are BACK to a single
straight DB.Line per bar (build_mat_bar_chains() dropped its curve-
bending entirely) and hooks are BACK to RebarHookType, via
get_hook_type_by_angle() (Phase 5.0) — same mechanism Phase 5.0 first
tried and that originally produced horizontal (wrong-plane) hooks.

The difference this time is Phase 5.3 finally root-caused THAT
original bug: Rebar.CreateFromCurves's `normal` argument defines the
PLANE the whole shape (hooks included) is considered to lie in — it is
NOT the direction a hook bends toward, which is what every previous
phase implicitly assumed. Passing a host face's normal (≈ ±Z for a
horizontal mat, what Phase 5.0/5.1 both did) tells Revit the shape's
plane is roughly HORIZONTAL, so it bends any hook WITHIN that
horizontal plane — sideways, out of the concrete. build_mat_bar_chains()
now computes and returns the CORRECT normal per bar direction via
rebar_engine.compute_vertical_hook_plane_normal(bar_direction) — the
normal of the VERTICAL plane containing the bar and the global Z axis —
so hooks bend vertically by construction. See that engine function's
own docstring for the full geometric reasoning, and
RebarWrapper.create_from_curves's updated `normal` parameter docs.

PHASE 5.4 — FULL-DEPTH U-BARS (RC DETAILING, EC2/BS8666 STYLE)
------------------------------------------------------------------
Phase 5.3's plane-normal fix worked — but live testing still showed
the TOP mat's RebarHookType hooks pointing the wrong way (up, into open
air, instead of down into the concrete). Rather than keep tuning
RebarHookOrientation.Left/Right blind, Phase 5.4 drops RebarHookType
for mats entirely and switches to an unambiguous, commercial-grade
detail: each mat bar's two ends become vertical LEGS running the
footing's own USABLE INTERNAL HEIGHT (thickness minus both covers) —
bottom mat legs reach UP toward the top mat, top mat legs reach DOWN
toward the bottom mat, closing the reinforcement cage across its full
depth. This is standard practice for thick foundations (a "full-depth
U-bar", not a short 90° anchorage hook) and, being built from explicit
geometry rather than an orientation enum, has no "which way does it
point" ambiguity left to get wrong.

Mechanically this is nothing new: build_mat_bar_chains() just calls
add_end_hooks() (Phase 2, unchanged) with the leg height in place of a
short hook length — a U-bar leg and a hook stub are the same geometry
shape, just different lengths. The leg height itself is computed once
in build_footing_reinforcement() from the host's own GLOBAL bounding
box (host.get_BoundingBox(None)) — the same technique
build_side_rebar_set's Phase 5.2 fix already proved reliable live —
rather than re-deriving footing depth from face-picking.

Dowels are UNCHANGED and still use RebarHookType (get_hook_type_by_angle)
— this message scoped the fix to mat bars specifically, and dowel hooks
were not reported broken.

build_mat_bars() and build_footing_rebar_curves() (Phase 2/4) are left
completely UNCHANGED below for any caller that still wants those
shapes.

PHASE 5.5 — BACK TO REBAR SETS FOR MATS (MULTI-REBAR ANNOTATION)
------------------------------------------------------------------
Phase 5.4's live test CONFIRMED the full-depth U-bar geometry AND the
vertical-plane normal both work — but it creates N individual Rebar
elements per direction, which blocks Multi-Rebar Annotation (MRA) and
schedule/quantity take-off tools that expect one countable Rebar Set
("range"), not N loose elements — unacceptable for a production RC-
detailing deliverable. Phase 5.5 adds build_mat_bar_set() — a Set-
based sibling of build_mat_bar_chains() returning ONE representative
U-bar shape plus `array_length_mm`/`spacing_mm` per direction, for
rebar_engine.RebarWrapper.create_rebar_set() (the same mechanism
build_side_rebar_set already uses successfully) instead of a loop of
create_from_curves calls. build_footing_reinforcement() now calls
build_mat_bar_set() instead of build_mat_bar_chains() — the latter is
left fully INTACT (Phase 5.4 proved it genuinely works) as a fallback
path, not dead code kept out of caution alone.

The key insight for why this Set attempt should succeed where Phase
5.1's failed: the SAME `normal` value that makes Rebar.CreateFromCurves
place a U-bar's legs in the correct vertical plane ALSO happens to be
the correct axis for ShapeDrivenAccessor to propagate the Set along
(both are "horizontal, perpendicular to the bar's own run direction").

PHASE 5.6 — THE HANDEDNESS BUG (POSITIONING) + Z-LAYERING (CLASH PREVENTION)
------------------------------------------------------------------
Phase 5.5's live test confirmed the Set mechanism DOES work for an
open U-bar shape (so Phase 5.1's failure was never fundamentally about
open-vs-closed shapes) — but ONE of the two mat directions came out as
two complete, duplicated Sets floating outside the footing (one above,
one below, for the bottom and top mat respectively), while the OTHER
direction was correct.

ROOT CAUSE: bar_dir x global-Z has a FIXED rotational handedness (turn
bar_dir -90 degrees around Z) — a bar along +X gives -Y, a bar along +Y
gives +X. Both mat directions need their Set to propagate FROM their
own starting edge INTO the footing (a positive-coordinate move), but
that one fixed handedness can only ever agree with ONE of the two
perpendicular directions — the other comes out backwards. Fixed via
rebar_engine.compute_vertical_hook_plane_normal()'s new
`propagation_reference` parameter, which checks and corrects the sign
per direction instead of trusting the raw cross product — see that
function's own Phase 5.6 note.

ALSO IN THIS PHASE: build_mat_bar_set() no longer takes a `face_info`
at all — X/Y AND Z now come entirely from host.get_BoundingBox(None),
removing any remaining dependency on a planar face's own UV
parametrization for the main mats (see that function's docstring for
the disclosed rotated-footing limitation this introduces, and why
build_mat_bar_chains — face-UV-based — would be the fallback's
fallback for a rotated footing specifically).

Z-LAYERING (clash prevention): the two perpendicular mat directions
can no longer share the exact same Z (they would physically clash) —
'along_x' is always Layer 1 (rests directly at the cover line),
'along_y' is always Layer 2 (rests ON Layer 1's own bars for the
bottom mat, or hangs BELOW Layer 1 for the top mat), each layer's Z
computed directly from the host's global bounding box plus the
relevant cover(s) and diameter(s) — see build_mat_bar_set()'s docstring
for the exact formulas. This also retires Phase 5.5's "mixed X/Y
diameters" DISCLOSED SIMPLIFICATION: each direction now genuinely uses
its own diameter for both its edge inset and its Z-layer position, no
more shared max(dia_x, dia_y) compromise.

Dowels remain unchanged and still use RebarHookType — out of scope for
this message.

PHASE 2.1 — PERIMETER CLOSURE U-BARS (CLASH-FREE DETAILING)
------------------------------------------------------------------
Adds build_perimeter_closure_ubar_sets(): additional Rebar Sets running
along all 4 plan edges of a footing/slab, each a vertical "U tumbada"
(back parallel to the concrete's side face, two horizontal legs
reaching into the slab) tying the bottom mat to the top mat at that
edge — B1<->T1 at the two edges where the along_x bars terminate,
B2<->T2 at the two edges where along_y terminates. Built with
add_end_hooks() exactly as build_mat_bar_set's own full-depth legs are,
just rotated 90 degrees (there the LINE is horizontal and the LEGS are
vertical; here the LINE is vertical and the LEGS are horizontal).
Requires a top mat (see that function's own docstring) — both
build_footing_reinforcement and floor_rebar.build_floor_reinforcement
raise a clear ValueError if requested without one, rather than
building a degenerate zero-height back.
"""
import math
import os
import sys

from Autodesk.Revit import DB
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_HERE = os.path.dirname(os.path.abspath(__file__))
# PHASE F2 — same sys.path convention as rebar_batch.py: this module can
# be loaded standalone (a legacy phase test script, or a stub-Revit dev
# environment) without the extension-wide lib/ dir already on sys.path.
_EXT_LIB = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _EXT_LIB not in sys.path:
    sys.path.insert(0, _EXT_LIB)

from nosa_utils import standards  # noqa: E402
from nosa_utils.telemetry import log_info as _log_info
re_engine = None  # populated by _ensure_engine(), so this file can be
                   # imported/py_compiled standalone without imp needing
                   # a live pyRevit session
slab_topology = None    # populated by _ensure_topology() — Phase 3.5.7
floor_rebar_mod = None  # populated by _ensure_floor_rebar() — Phase 3.5.7
column_rebar_mod = None  # populated by _ensure_column_rebar()


def _ensure_engine():
    global re_engine
    if re_engine is None:
        # PHASE F0 — migrated from imp.load_source to
        # nosa_utils.bootstrap.load_module. Registered name unchanged.
        from nosa_utils.bootstrap import load_module
        re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
    return re_engine


def _ensure_topology():
    """PHASE 3.5.7 item 3 — lazy-load slab_topology.py, the same
    pure-geometry module floor_rebar.py already uses for real boundary
    extraction/hole detection/offsetting — footings now use it too
    (see build_mat_bars_topology / build_perimeter_closure_ubars_topology),
    instead of the old host.get_BoundingBox(None)-only rectangular
    assumption that ignored holes entirely."""
    global slab_topology
    if slab_topology is None:
        from nosa_utils.bootstrap import load_module
        slab_topology = load_module(
            'slab_topology', os.path.join(_HERE, 'slab_topology.py'))
    return slab_topology


def _ensure_column_rebar():
    """Lazy-load column_rebar.py (its section detector), same pattern as _ensure_floor_rebar."""
    global column_rebar_mod
    if column_rebar_mod is None:
        from nosa_utils.bootstrap import load_module
        column_rebar_mod = load_module('column_rebar', os.path.join(_HERE, 'column_rebar.py'))
    return column_rebar_mod


def _ensure_floor_rebar():
    """PHASE 3.5.7 item 3 — lazy-load floor_rebar.py so footings can
    reuse its ALREADY-TESTED, shape-agnostic topology-based bar
    generators (_build_direction_bars, _build_edge_ubars) directly,
    rather than re-deriving the same real-boundary/hole-clipping logic
    a second time. Safe against circular loading: this is only ever
    called from inside a function (never at either module's own
    top-level), and floor_rebar.py's own _ensure_footing_rebar() is
    equally lazy — by the time either side's lazy loader actually
    fires, both modules already fully exist as independent objects in
    sys.modules (ui.py loads both at its own module scope before
    either function body ever runs)."""
    global floor_rebar_mod
    if floor_rebar_mod is None:
        from nosa_utils.bootstrap import load_module
        floor_rebar_mod = load_module(
            'floor_rebar', os.path.join(_HERE, 'floor_rebar.py'))
    return floor_rebar_mod


_MM_PER_FT = 304.8


def _lookup_length_param_mm(host, names):
    """Same contract as column_rebar._lookup_length_param_mm —
    duplicated here (not imported) so this module stays self-contained
    per its own established pattern (see e.g. _evenly_spaced,
    duplicated identically across this project's modules)."""
    candidates = [host]
    try:
        symbol = getattr(host, 'Symbol', None)
        if symbol is not None:
            candidates.append(symbol)
    except Exception:
        log_swallowed(_LOG, u'_lookup_length_param_mm')
    for elem in candidates:
        for name in names:
            try:
                param = elem.LookupParameter(name)
            except Exception:
                param = None
            if param is None:
                continue
            try:
                value_ft = param.AsDouble()
            except Exception:
                value_ft = None
            if value_ft is not None and value_ft > 0:
                return value_ft * _MM_PER_FT
    return None


def _footing_bbox(host):
    """
    PHASE 3.5.6 item 2 — the footing/pile-cap's OWN bounding box,
    isolated from any nested pile geometry (rebar_engine.
    get_isolated_solid_bbox), replacing every host.get_BoundingBox(None)
    call in this module — that call reflects the WHOLE family
    instance's extent, including nested FamilyInstances (piles nested
    inside a pile-cap family), which was silently pulling Min.Z down
    to the pile tips and corrupting every Z/X/Y calculation built on
    it. Falls back to host.get_BoundingBox(None) (pre-3.5.6 behaviour)
    only if the isolated solid isn't readable (e.g. a footing with no
    nested geometry at all, where the distinction doesn't matter, or a
    mocked/test host).

    As a non-fatal safety net (Phase 3.5.6), cross-checks the isolated
    bbox's own plan/thickness dimensions against this element's
    "Width"/"Length"/"Foundation Thickness" TYPE parameters, if
    present, and prints a console warning on a large (>2x) mismatch —
    a WARNING only, never overriding the geometry, since footing
    family parameter naming is far less standardised than a column's
    b/h and isn't a source this module trusts blindly.
    """
    engine = _ensure_engine()
    bbox = engine.get_isolated_solid_bbox(host)
    if bbox is None:
        bbox = host.get_BoundingBox(None)
    if bbox is None:
        return None

    plan_mm = ((bbox.Max.X - bbox.Min.X) * _MM_PER_FT, (bbox.Max.Y - bbox.Min.Y) * _MM_PER_FT)
    thickness_mm = (bbox.Max.Z - bbox.Min.Z) * _MM_PER_FT
    for name in (u'Width', u'Length', u'Foundation Thickness'):
        param_mm = _lookup_length_param_mm(host, [name])
        if param_mm is None:
            continue
        # Plan dimensions are checked against the closer bbox side: a rotated
        # family or a strip footing (Width across the wall) swaps X and Y.
        geom_mm = thickness_mm if name == u'Foundation Thickness' else             min(plan_mm, key=lambda g: abs(g - param_mm))
        if geom_mm <= 0:
            continue
        if param_mm > geom_mm * 2.0 or geom_mm > param_mm * 2.0:
            _log_info(u'rebarautomate', u'WARNING [footing_rebar]: isolated-solid {} ({:.0f}mm) differs '
                  u'from the "{}" type parameter ({:.0f}mm) by more than 2x — '
                  u'verify this footing\'s geometry/parameters are consistent.'.format(
                      name.lower(), geom_mm, name, param_mm))
    return bbox


# ══════════════════════════════════════════════════════════════════════════
# Face discovery
# ══════════════════════════════════════════════════════════════════════════

def get_footing_bottom_face(cover_mgr):
    """
    The footing's bottom face, classified by its normal pointing
    downward (Z component below -0.7 — matches this module's flat/
    near-flat footing scope; a genuinely sloped footing underside would
    fail this test and return None rather than a wrong face).

    Args:
        cover_mgr (rebar_engine.CoverGeometryManager): built for the
            footing host.

    Returns:
        rebar_engine.HostFaceInfo, or None if no clearly-downward face
        was found among the host's planar faces.
    """
    best = None
    for face_info in cover_mgr.faces:
        if face_info.normal.Z < -0.7:
            if best is None or face_info.normal.Z < best.normal.Z:
                best = face_info
    return best


def get_footing_top_face(cover_mgr):
    """
    The footing's top face, classified by its normal pointing upward
    (Z component above +0.7 — the mirror image of
    get_footing_bottom_face's -0.7 threshold, same flat/near-flat
    scope). Used by Phase 5's top mat.

    Args:
        cover_mgr (rebar_engine.CoverGeometryManager): built for the
            footing host.

    Returns:
        rebar_engine.HostFaceInfo, or None if no clearly-upward face
        was found.
    """
    best = None
    for face_info in cover_mgr.faces:
        if face_info.normal.Z > 0.7:
            if best is None or face_info.normal.Z > best.normal.Z:
                best = face_info
    return best


# ══════════════════════════════════════════════════════════════════════════
# Orthogonal grid
# ══════════════════════════════════════════════════════════════════════════

def _evenly_spaced(lo, hi, spacing):
    """
    Positions between lo and hi (inclusive), spaced no further apart
    than `spacing`, distributed EVENLY across the full span — same
    "no odd short leftover gap" philosophy as
    rebar_engine.split_rebar_by_stock_length. A span shorter than
    `spacing` returns just its midpoint (one bar, centred).
    """
    span = hi - lo
    if span <= 0:
        return []
    if span <= spacing:
        return [(lo + hi) / 2.0]
    # ceil (not floor) here: the number of GAPS must be enough that no
    # single gap exceeds `spacing` — e.g. span=1000, spacing=150 needs
    # ceil(1000/150)=7 gaps (8 positions, ~142.9mm apart), not floor's 6
    # gaps (which would give ~166.7mm apart, violating the max-spacing
    # contract this function promises).
    n = int(math.ceil(span / spacing)) + 1
    actual_spacing = span / float(n - 1)
    return [lo + i * actual_spacing for i in range(n)]


def generate_orthogonal_grid(face_info, cover_mm, spacing_x_mm, spacing_y_mm,
                              bar_diameter_mm=0.0, edge_cover_mm=None):
    """
    Generate an orthogonal (U/V) reinforcement grid over a planar face —
    typically the footing's bottom face — inset from every edge by
    edge_cover_mm (defaults to cover_mm, the same nominal cover value,
    if not given separately) plus half the bar diameter.

    Works in the face's OWN UV coordinate system (via Face.Evaluate),
    not global X/Y — a footing rotated in plan still gets a correctly
    rotated grid, since "along U" / "along V" always means "parallel to
    this face's own local axes."

    The returned lines lie ON the face itself (in-plane only) — callers
    that also need the perpendicular cover offset off the bottom
    SURFACE (bars sitting above the concrete face, not on it) should
    pass each line through rebar_engine.offset_curve_inward(line,
    face_info, cover_mm) — see build_footing_rebar_curves() for the
    full pipeline that does this.

    Args:
        face_info        (rebar_engine.HostFaceInfo): typically from
                          get_footing_bottom_face().
        cover_mm          (float): nominal cover, mm.
        spacing_x_mm      (float): max spacing for bars running along
                          the face's V axis (i.e. the "X-direction"
                          bars, each at a fixed U, distributed along U).
        spacing_y_mm      (float): max spacing for bars running along
                          the face's U axis, distributed along V.
        bar_diameter_mm   (float): used only for the edge inset (half
                          the bar sits inside the nominal cover line).
        edge_cover_mm     (float or None): edge/side cover if different
                          from the bottom cover_mm; defaults to cover_mm.

    Returns:
        {'bars_along_u': list[DB.Line], 'bars_along_v': list[DB.Line]}
        — 'bars_along_u' bars run in the face's U direction (each
        spans the full U range at a fixed V, so there is one per V
        position); 'bars_along_v' bars run in V (one per U position).
        Either list may be empty if the face is too small for the given
        cover/diameter to fit even one bar.
    """
    if edge_cover_mm is None:
        edge_cover_mm = cover_mm

    inset_ft = (edge_cover_mm + bar_diameter_mm / 2.0) / _MM_PER_FT
    bbox = face_info.face.GetBoundingBox()
    u0, u1 = bbox.Min.U + inset_ft, bbox.Max.U - inset_ft
    v0, v1 = bbox.Min.V + inset_ft, bbox.Max.V - inset_ft
    if u1 <= u0 or v1 <= v0:
        return {'bars_along_u': [], 'bars_along_v': []}

    spacing_x_ft = spacing_x_mm / _MM_PER_FT
    spacing_y_ft = spacing_y_mm / _MM_PER_FT

    bars_along_u = []
    for v in _evenly_spaced(v0, v1, spacing_y_ft):
        p0 = face_info.face.Evaluate(DB.UV(u0, v))
        p1 = face_info.face.Evaluate(DB.UV(u1, v))
        bars_along_u.append(DB.Line.CreateBound(p0, p1))

    bars_along_v = []
    for u in _evenly_spaced(u0, u1, spacing_x_ft):
        p0 = face_info.face.Evaluate(DB.UV(u, v0))
        p1 = face_info.face.Evaluate(DB.UV(u, v1))
        bars_along_v.append(DB.Line.CreateBound(p0, p1))

    return {'bars_along_u': bars_along_u, 'bars_along_v': bars_along_v}


# ══════════════════════════════════════════════════════════════════════════
# Hooks / anchorage
# ══════════════════════════════════════════════════════════════════════════

def default_anchorage_length_mm(bar_diameter_mm, multiplier=40.0, std=None,
                                 good_bond=True, in_compression=False):
    """
    A simple bar-diameter-multiple ESTIMATE of anchorage/hook length.

    This is NOT a full EC2 anchorage-length calculation. The real
    formula (lb,rqd = phi/4 * sigma_sd/f_bd, then lbd = alpha1..alpha5 *
    lb,rqd >= lb,min) needs the concrete class, bar surface/bond
    condition, and several alpha coefficients this module has no access
    to and should not guess. multiplier=40 is a commonly-used rough
    default for a "good bond condition" scenario, adequate for
    preliminary layout — a caller doing real code-compliance detailing
    should supply a project-specific multiplier derived from a proper
    EC2/National-Annex lookup (or a BS 8666 table), not rely on this
    default for anything beyond that.

    Args:
        bar_diameter_mm (float)
        multiplier       (float): anchorage length as a multiple of
                          bar diameter, default 40.

    Returns:
        float: anchorage length in mm.

    PHASE F2 — compat wrapper: when `std` (a resolved
    nosa_utils.standards profile dict) is supplied, delegates to
    standards.anchorage_length_mm(std, bar_diameter_mm, good_bond,
    in_compression) instead, so a caller that has resolved a normativa
    gets that normativa's real anchorage factors. Every existing
    caller that omits `std` (the default, None) is completely
    unaffected — same bar_diameter_mm * multiplier as before this
    phase.
    """
    if std is not None:
        return standards.anchorage_length_mm(std, bar_diameter_mm, good_bond, in_compression)
    return bar_diameter_mm * multiplier


def default_lap_mm(bar_diameter_mm, std=None, good_bond=True, pct_lapped=100.0):
    """Lap length (EC2 / BS 8110 through std, else 40 phi), never below max(15 phi, 300 mm)."""
    if std is not None:
        return standards.lap_length_mm(std, bar_diameter_mm, False, pct_lapped, good_bond)
    return max(40.0 * bar_diameter_mm, 15.0 * bar_diameter_mm, 300.0)


def good_bond_for_top_bars(host_depth_mm):
    """EC2 8.4.2 / Fig. 8.2: top bars of members deeper than 250 mm are in poor bond."""
    return host_depth_mm <= 250.0


def add_end_hooks(line, hook_length_mm, direction, at_start=False, at_end=False):
    """
    Return `line` as a curve CHAIN (list of DB.Line) with a straight
    hook stub of hook_length_mm appended at the requested end(s), bent
    toward `direction` (e.g. DB.XYZ.BasisZ for a footing bar hooking up
    into the footing's depth).

    This produces a simple straight-segment "L hook" — enough to route
    material quantity and reserve the anchorage length in the model. It
    is NOT a curved/rounded hook radius; where an accurately rendered
    Revit hook matters more than raw geometry, prefer passing a
    RebarHookType to rebar_engine.RebarWrapper.create_from_curves's
    start_hook/end_hook instead of this function's stub geometry — the
    two approaches solve the same problem at different fidelity and a
    caller should pick one, not both, for the same bar end.

    Args:
        line            (DB.Line): the main bar segment.
        hook_length_mm  (float): hook stub length, mm — see
                        default_anchorage_length_mm() for an estimate.
        direction       (DB.XYZ): unit vector the hook bends toward.
        at_start        (bool): add a hook at line's start (end 0).
        at_end          (bool): add a hook at line's end (end 1).

    Returns:
        list[DB.Line]: [start_hook?, main_line, end_hook?] — always at
        least [main_line] if neither flag is set.
    """
    hook_ft = hook_length_mm / _MM_PER_FT
    direction = direction.Normalize()
    chain = []

    if at_start:
        p0 = line.GetEndPoint(0)
        hook_start = p0 + direction.Multiply(hook_ft)
        chain.append(DB.Line.CreateBound(hook_start, p0))

    chain.append(line)

    if at_end:
        p1 = line.GetEndPoint(1)
        hook_end = p1 + direction.Multiply(hook_ft)
        chain.append(DB.Line.CreateBound(p1, hook_end))

    return chain


# ══════════════════════════════════════════════════════════════════════════
# Orchestration
# ══════════════════════════════════════════════════════════════════════════

def build_footing_rebar_curves(doc, host, cover_mm, spacing_x_mm, spacing_y_mm,
                                bar_diameter_mm=16.0, edge_cover_mm=None,
                                add_hooks=False, hook_multiplier=40.0):
    """
    High-level pipeline for one footing host: cover manager -> bottom
    face -> in-plane grid -> perpendicular cover offset -> optional
    end hooks. Returns curve CHAINS ready to feed into
    rebar_engine.RebarWrapper.create_from_curves (one call per chain).

    Args:
        doc              (DB.Document)
        host             (DB.Element): the footing (isolated pad or
                         strip) to reinforce.
        cover_mm         (float): bottom cover, mm.
        spacing_x_mm, spacing_y_mm (float): grid spacing in each
                         direction, mm — see generate_orthogonal_grid().
        bar_diameter_mm  (float): used for the grid's edge inset and,
                         if add_hooks, passed through to
                         default_anchorage_length_mm().
        edge_cover_mm    (float or None): edge cover if different from
                         cover_mm.
        add_hooks        (bool): if True, both ends of every grid bar
                         get a straight hook stub bent upward
                         (DB.XYZ.BasisZ), sized via
                         default_anchorage_length_mm(bar_diameter_mm,
                         hook_multiplier).
        hook_multiplier  (float): passed to default_anchorage_length_mm.

    Returns:
        {
          'bars_along_u': list[list[DB.Curve]],
          'bars_along_v': list[list[DB.Curve]],
        }
        Each inner list is one bar's curve chain — a single-element
        [line] if add_hooks is False, or [hook, line, hook] if True.

    Raises:
        ValueError: if the host has no identifiable downward-facing
        bottom face (see get_footing_bottom_face()).
    """
    engine = _ensure_engine()
    cover_mgr = engine.CoverGeometryManager(doc, host)
    bottom_face = get_footing_bottom_face(cover_mgr)
    if bottom_face is None:
        raise ValueError(
            u'Could not find a clearly downward-facing bottom face on this '
            u'footing — is it flat-soffit? Sloped/stepped footings are not '
            u'supported by this module yet.')

    raw_grid = generate_orthogonal_grid(
        bottom_face, cover_mm, spacing_x_mm, spacing_y_mm,
        bar_diameter_mm, edge_cover_mm)

    result = {'bars_along_u': [], 'bars_along_v': []}
    hook_len_mm = default_anchorage_length_mm(bar_diameter_mm, hook_multiplier)

    for key in ('bars_along_u', 'bars_along_v'):
        for raw_line in raw_grid[key]:
            offset_line = engine.offset_curve_inward(raw_line, bottom_face, cover_mm)
            if add_hooks:
                chain = add_end_hooks(offset_line, hook_len_mm, DB.XYZ.BasisZ,
                                       at_start=True, at_end=True)
            else:
                chain = [offset_line]
            result[key].append(chain)

    return result


# ══════════════════════════════════════════════════════════════════════════
# PHASE 5 — Mat builder (bottom + top), dowels, and full orchestration
# ══════════════════════════════════════════════════════════════════════════
#
# See the module docstring's "PHASE 5 — HOOKS ARE AN ENGINE-LEVEL CONCERN"
# note: everything below returns single straight DB.Line bars (never a
# pre-bent curve chain) plus enough metadata (a `hooks` flag and the
# relevant face's outward normal) for the caller to request real
# RebarHookType hooks from rebar_engine.RebarWrapper.create_from_curves
# at bar-creation time.

def build_mat_bars(face_info, cover_mm, spacing_x_mm, spacing_y_mm,
                    bar_diameter_mm, edge_cover_mm=None):
    """
    A full orthogonal reinforcement mat over ONE planar face (bottom or
    top), as single straight DB.Line bars already offset inward from
    the face by cover_mm — the Phase 5 replacement for the inner loop
    of build_footing_rebar_curves, generalised to work on either the
    bottom or the top face (whichever `face_info` is) and without any
    hook geometry (see module docstring).

    Args:
        face_info        (rebar_engine.HostFaceInfo): the mat's face —
                         get_footing_bottom_face() or
                         get_footing_top_face()'s result.
        cover_mm          (float): cover for THIS face, mm — bottom and
                         top mats normally use different cover values,
                         so the caller passes whichever applies.
        spacing_x_mm, spacing_y_mm (float): grid spacing in each
                         direction, mm — see generate_orthogonal_grid().
        bar_diameter_mm  (float): used for the grid's edge inset.
        edge_cover_mm    (float or None): edge cover if different from
                         cover_mm.

    Returns:
        {
          'bars_along_u': list[DB.Line],
          'bars_along_v': list[DB.Line],
          'face_normal':  DB.XYZ,   # face_info.normal, passed straight
                                    # through for the caller's `normal`
                                    # argument to create_from_curves
        }
    """
    engine = _ensure_engine()
    raw_grid = generate_orthogonal_grid(
        face_info, cover_mm, spacing_x_mm, spacing_y_mm, bar_diameter_mm, edge_cover_mm)

    result = {'bars_along_u': [], 'bars_along_v': [], 'face_normal': face_info.normal}
    for key in ('bars_along_u', 'bars_along_v'):
        for raw_line in raw_grid[key]:
            result[key].append(engine.offset_curve_inward(raw_line, face_info, cover_mm))
    return result


def build_mat_bar_chains(face_info, cover_mm, spacing_x_mm, spacing_y_mm,
                          bar_diameter_mm, leg_height_mm=0.0, leg_direction=None,
                          edge_cover_mm=None):
    """
    PHASE 5.4 — RC-DETAILING-GRADE FULL-DEPTH U-BARS.

    Phase 5.3's RebarHookType hooks fixed the plane-normal bug but still
    left the top mat's hooks pointing the wrong way in the live model
    (up instead of down) — a RebarHookOrientation guess this project
    never had a reliable way to pin down without more live iteration.
    Rather than keep guessing an enum, Phase 5.4 switches to explicit,
    unambiguous geometry: each bar's two ends become vertical LEGS that
    run the full USABLE INTERNAL HEIGHT of the footing (bottom mat legs
    reach UP toward the top mat; top mat legs reach DOWN toward the
    bottom mat — see build_footing_reinforcement's Phase 5.4 section for
    how leg_height_mm/leg_direction are computed from the footing's own
    thickness), closing the reinforcement cage across its full depth —
    standard EC2/BS8666 "full-depth U-bar" detailing for thick
    foundations, rather than a short standard 90° hook.

    Internally this reuses add_end_hooks() (Phase 2) UNCHANGED — a U-bar
    leg is geometrically identical to a hook, just with the "hook
    length" set to the footing's usable internal height instead of a
    short anchorage stub. If leg_height_mm is 0 (or leg_direction is
    None), bars stay plain single Lines exactly as Phase 5.3 left them.

    RISK DISCLOSURE — 3-curve chains via create_from_curves (not a Rebar
    Set) were reported failing once already in this project (Phase
    5.2), attributed at the time to "Revit rejecting orthogonal corners
    with no fillet." That attempt used the WRONG plane normal (a face
    normal, not this module's now-corrected
    compute_vertical_hook_plane_normal() result) — since a shape's
    curves must actually lie IN the plane declared by `normal`, a wrong
    normal for a genuinely-vertical U-shape may itself have been
    sufficient to make Revit reject the whole shape, independent of any
    fillet/corner-radius question. This phase's bet is that the
    corrected normal (already confirmed working for plain straight bars
    in Phase 5.3) resolves this too. If mats STILL fail to generate with
    this 3-curve U-shape, the next thing to check is whether
    leg_height_mm is large enough to satisfy the RebarBarType's own
    minimum bend/fillet radius requirement — not the normal or the
    curve count again.

    Args:
        face_info        (rebar_engine.HostFaceInfo): the mat's face.
        cover_mm          (float): cover for THIS face, mm.
        spacing_x_mm, spacing_y_mm (float): grid spacing in each
                         direction, mm — see generate_orthogonal_grid().
        bar_diameter_mm  (float): used for the edge inset.
        leg_height_mm    (float): full-depth U-bar leg length, mm — 0
                         (default) means no legs (plain straight bars).
        leg_direction    (DB.XYZ or None): unit vector the legs extend
                         toward — DB.XYZ.BasisZ for the bottom mat
                         (legs go UP), DB.XYZ.BasisZ.Multiply(-1.0) for
                         the top mat (legs go DOWN). Required if
                         leg_height_mm > 0.
        edge_cover_mm    (float or None): edge cover if different from
                         cover_mm.

    Returns:
        {
          'bars_along_u': list[list[DB.Curve]],  # each inner list is a
                          1-element [line] chain (no legs) or a
                          3-element [leg, line, leg] U-bar chain, ready
                          for RebarWrapper.create_from_curves.
          'bars_along_v': list[list[DB.Curve]],
          'normal_along_u': DB.XYZ or None,  # the correct
                          Rebar.CreateFromCurves `normal` for EVERY bar
                          in 'bars_along_u' — None if that direction
                          has no bars (face too small).
          'normal_along_v': DB.XYZ or None,
        }
    """
    engine = _ensure_engine()
    mat = build_mat_bars(face_info, cover_mm, spacing_x_mm, spacing_y_mm,
                          bar_diameter_mm, edge_cover_mm)

    def _direction_normal(lines):
        if not lines:
            return None
        bar_dir = (lines[0].GetEndPoint(1) - lines[0].GetEndPoint(0)).Normalize()
        return engine.compute_vertical_hook_plane_normal(bar_dir)

    use_legs = bool(leg_height_mm) and leg_direction is not None

    def _chains(lines):
        if use_legs:
            return [add_end_hooks(line, leg_height_mm, leg_direction, at_start=True, at_end=True)
                    for line in lines]
        return [[line] for line in lines]

    return {
        'bars_along_u': _chains(mat['bars_along_u']),
        'bars_along_v': _chains(mat['bars_along_v']),
        'normal_along_u': _direction_normal(mat['bars_along_u']),
        'normal_along_v': _direction_normal(mat['bars_along_v']),
    }


def build_mat_bar_set(host, is_top, cover_mm, dia_x_mm, dia_y_mm,
                       spacing_x_mm, spacing_y_mm,
                       target_z_mm=None, leg_direction=None):
    """
    *** ALSO USED BY floor_rebar.py (RebarAutomate Phase 2) *** — this
    function takes only a plain `host` and works entirely off
    host.get_BoundingBox(None), with nothing footing-specific in its
    body, so floor_rebar.build_floor_reinforcement calls it directly
    (loaded as a sibling module) instead of re-deriving the same
    geometry for OST_Floors — see that module's own docstring for why.
    Keep that in mind before changing this function's behaviour: a
    "footing-only" fix here would silently also change floor slabs.

    PHASE 5.6 — GLOBAL COORDINATES + Z-LAYERING (CLASH PREVENTION).

    Phase 5.5's live test found ONE of the two mat directions correct
    (visible, in-place mesh) and the OTHER producing two complete,
    duplicated Rebar Sets floating outside the footing, offset in X/Y —
    for BOTH the bottom and top mat (hence "two" sets, one high, one
    low). Root cause, found while implementing this fix: the plane
    normal from bar_dir x global-Z has a FIXED rotational handedness
    (turn bar_dir -90 deg around Z) — for a bar running along +X this
    gives -Y, for a bar running along +Y this gives +X. Both mat
    directions need their Set to propagate FROM their own starting edge
    INTO the footing (a positive-coordinate direction), but that one
    fixed rotational sense can only ever match ONE of the two
    perpendicular directions — the other comes out backwards, sending
    that whole Set outside the footing. This is exactly the reported
    symptom. Fixed here by passing a `propagation_reference` to
    rebar_engine.compute_vertical_hook_plane_normal() so its sign is
    checked and corrected per direction, not assumed from the cross
    product alone.

    ALSO NEW — this function no longer takes a `face_info` at all: X/Y
    AND Z now come ENTIRELY from host.get_BoundingBox(None), the same
    global, axis-aligned technique already proven reliable for
    build_side_rebar_set's Z (and, per that function's own live-tested
    success, for its X/Y too). This removes any dependency on a planar
    face's own UV parametrization for the main mats. DISCLOSED
    LIMITATION: a footing ROTATED relative to the project's X/Y axes
    would get a global AABB LARGER than its true rotated footprint,
    placing bars wrong — this module's whole SCOPE has always assumed
    simple rectangular pad/strip footings, and this phase additionally
    assumes they are not rotated in plan. build_mat_bar_chains (Phase
    5.4, face-UV-based, kept intact) would need to be the starting
    point for a rotated-footing variant, not this function.

    Z-LAYERING (clash prevention): the two perpendicular directions
    cannot occupy the exact same Z without clashing — one must rest on
    (bottom mat) or hang below (top mat) the other. This function's
    fixed convention: 'along_x' is always LAYER 1 (its own bars sit
    directly at the cover line), 'along_y' is always LAYER 2 (sits ON
    TOP of layer 1's own bars for the bottom mat, or hangs BELOW layer
    1 for the top mat) — an arbitrary but consistent, disclosed choice,
    since the brief did not tie a specific physical direction to "outer
    layer." Concretely, with Zmin/Zmax the host's own global bounding
    box extents:
        Bottom mat (is_top=False):
            z_layer1 = Zmin + cover_mm + dia_x_mm/2
            z_layer2 = Zmin + cover_mm + dia_x_mm + dia_y_mm/2      (rests on layer 1)
        Top mat (is_top=True):
            z_layer1 = Zmax - cover_mm - dia_x_mm/2
            z_layer2 = Zmax - cover_mm - dia_x_mm - dia_y_mm/2   (hangs below layer 1)
    These are bar CENTRELINES (T2.10b, 2026-09-30: the old values were a
    radius off, so the bottom X layer broke cover and Y overlapped X).

    Args:
        host             (DB.Element): the footing.
        is_top           (bool): False for the bottom mat, True for the
                         top mat — selects which Z-layering formula
                         above applies.
        cover_mm         (float): cover for THIS mat, mm.
        dia_x_mm, dia_y_mm (float): bar diameter for 'along_x'
                         (Layer 1) and 'along_y' (Layer 2) respectively
                         — used for BOTH the Z-layering above and each
                         direction's own edge inset (no more shared
                         max(dia_x, dia_y) compromise: Phase 5.5's
                         single-diameter DISCLOSED SIMPLIFICATION no
                         longer applies, since each direction now
                         genuinely uses its own diameter throughout).
        spacing_x_mm, spacing_y_mm (float): MAXIMUM spacing for each
                         direction's Set, mm — spacing_y_mm governs
                         'along_x' (propagated along Y), spacing_x_mm
                         governs 'along_y' (propagated along X), same
                         convention as generate_orthogonal_grid.
        target_z_mm      (float or None): if given (together with
                         leg_direction), each layer's bars get a
                         full-depth U-bar leg reaching from ITS OWN Z
                         to this target elevation (so layer 1 and layer
                         2 have slightly different leg lengths, since
                         they start from slightly different Z — the
                         same one-bar-diameter offset the Z-layering
                         above introduces). None means plain single-Line
                         bars (no legs).
        leg_direction    (DB.XYZ or None): unit vector the legs extend
                         toward — DB.XYZ.BasisZ for the bottom mat,
                         DB.XYZ.BasisZ.Multiply(-1.0) for the top mat.
                         Required if target_z_mm is given.

    Returns:
        {
          'along_x': {'curves': [DB.Curve,...], 'normal': DB.XYZ,
                      'array_length_mm': float, 'spacing_mm': float}
                      or None if the footing is too small to fit even
                      one bar at this cover/diameter,
          'along_y': same shape, or None,
        }

    Raises:
        ValueError: if the host's global bounding box can't be read.
    """
    engine = _ensure_engine()
    global_bbox = _footing_bbox(host)
    if global_bbox is None:
        raise ValueError(u'Could not read this footing\'s global bounding box.')

    inset_x_ft = (cover_mm + dia_x_mm / 2.0) / _MM_PER_FT
    inset_y_ft = (cover_mm + dia_y_mm / 2.0) / _MM_PER_FT
    x0 = global_bbox.Min.X + inset_x_ft
    x1 = global_bbox.Max.X - inset_x_ft
    y0 = global_bbox.Min.Y + inset_y_ft
    y1 = global_bbox.Max.Y - inset_y_ft

    result = {'along_x': None, 'along_y': None}
    if x1 <= x0 or y1 <= y0:
        return result

    if is_top:
        z_layer1_ft = global_bbox.Max.Z - (cover_mm + dia_x_mm / 2.0) / _MM_PER_FT
        z_layer2_ft = global_bbox.Max.Z - (cover_mm + dia_x_mm + dia_y_mm / 2.0) / _MM_PER_FT
    else:
        z_layer1_ft = global_bbox.Min.Z + (cover_mm + dia_x_mm / 2.0) / _MM_PER_FT
        z_layer2_ft = global_bbox.Min.Z + (cover_mm + dia_x_mm + dia_y_mm / 2.0) / _MM_PER_FT

    use_legs = target_z_mm is not None and leg_direction is not None
    target_z_ft = (target_z_mm / _MM_PER_FT) if use_legs else None

    def _bar_chain(p0, p1, own_z_ft):
        line = DB.Line.CreateBound(p0, p1)
        if not use_legs:
            return [line]
        leg_len_mm = abs(target_z_ft - own_z_ft) * _MM_PER_FT
        return add_end_hooks(line, leg_len_mm, leg_direction, at_start=True, at_end=True)

    # 'along_x' (Layer 1): one bar spanning the full X range at y0,
    # propagated toward y1 — INTO the footing.
    p_x0 = DB.XYZ(x0, y0, z_layer1_ft)
    p_x1 = DB.XYZ(x1, y0, z_layer1_ft)
    normal_x = engine.compute_vertical_hook_plane_normal(
        DB.XYZ(1.0, 0.0, 0.0), propagation_reference=DB.XYZ(0.0, 1.0, 0.0))
    result['along_x'] = {
        'curves': _bar_chain(p_x0, p_x1, z_layer1_ft),
        'normal': normal_x,
        'array_length_mm': (y1 - y0) * _MM_PER_FT,
        'spacing_mm': spacing_y_mm,
    }

    # 'along_y' (Layer 2): one bar spanning the full Y range at x0,
    # propagated toward x1 — INTO the footing.
    p_y0 = DB.XYZ(x0, y0, z_layer2_ft)
    p_y1 = DB.XYZ(x0, y1, z_layer2_ft)
    normal_y = engine.compute_vertical_hook_plane_normal(
        DB.XYZ(0.0, 1.0, 0.0), propagation_reference=DB.XYZ(1.0, 0.0, 0.0))
    result['along_y'] = {
        'curves': _bar_chain(p_y0, p_y1, z_layer2_ft),
        'normal': normal_y,
        'array_length_mm': (x1 - x0) * _MM_PER_FT,
        'spacing_mm': spacing_x_mm,
    }
    return result


def build_perimeter_closure_ubar_sets(host,
                                       bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
                                       top_cover_mm, top_dia_x_mm, top_dia_y_mm,
                                       x_anchor_dia_mm, x_anchor_spacing_mm,
                                       y_anchor_dia_mm, y_anchor_spacing_mm,
                                       edge_cover_mm=None, leg_length_mm=None):
    """
    *** ALSO USED BY floor_rebar.py *** — same host-agnostic,
    host.get_BoundingBox(None)-only convention as build_mat_bar_set
    above (see that function's own note on cross-module reuse).

    PHASE 2.1 — PERIMETER CLOSURE U-BARS (CLASH-FREE DETAILING).

    A "U tumbada" (lying-down U, lying in a VERTICAL plane
    PERPENDICULAR to the perimeter edge it sits on) closing the main
    mat's reinforcement at each of the footing/slab's 4 plan edges:
    a vertical "back" segment parallel to the concrete's side face,
    with two horizontal "legs" both reaching INTO the slab — one at
    the bottom mat's own layer elevation, one at the top mat's — tying
    B1 to T1 (at the two edges where the along_x main bars terminate)
    or B2 to T2 (at the two edges where the along_y main bars
    terminate). Confirmed geometry per this phase's design discussion:
    the back's two ends ARE the legs' anchor points, so this is built
    with add_end_hooks() exactly as build_mat_bar_set's own full-depth
    legs are — a vertical `line` (the back) with a hook (leg) at each
    end, both bending toward the same horizontal `direction` (into the
    slab) — just re-oriented 90 degrees from that other use (there,
    the LINE is horizontal and the LEGS are vertical; here, the LINE
    is vertical and the LEGS are horizontal).

    ANTI-CLASH BY CONSTRUCTION: the x-edge U-bars (anchoring B1/T1)
    and the y-edge U-bars (anchoring B2/T2) automatically avoid
    colliding at the corners for exactly the same reason the main
    B1/B2 (and T1/T2) mat layers themselves don't clash — they sit at
    different Z (B2/T2 are offset from B1/T1 by one bar diameter, per
    build_mat_bar_set's own Z-layering) — no separate corner-avoidance
    logic is needed here beyond reusing those same Z values.

    REQUIRES A TOP MAT: since every closure U-bar's back spans from a
    bottom-mat layer's Z to the CORRESPONDING top-mat layer's Z, this
    function has no meaning without a top mat present — callers must
    only invoke it when include_top_mat is True (see
    build_footing_reinforcement / build_floor_reinforcement, which
    raise a clear ValueError if a caller requests this without a top
    mat, rather than silently building a degenerate/zero-height back).

    DISCLOSED SIMPLIFICATION — leg length: this module has no anchorage
    length calculation more precise than default_anchorage_length_mm's
    "40x bar diameter" rule of thumb (see that function's own docstring
    for why); leg_length_mm defaults to exactly that, per this closure
    U-bar's OWN diameter (x_anchor_dia_mm / y_anchor_dia_mm as
    applicable), not a project-specific EC2 anchorage-length
    calculation. A caller doing real code-compliance detailing should
    pass an explicit leg_length_mm instead of relying on this default.

    DISCLOSED SIMPLIFICATION — edge/propagation inset: both the
    U-bar's own lateral position (how far its "back" sits inside the
    true concrete edge) and the propagation range along that edge
    reuse the SAME edge_cover_mm value (defaulting to bottom_cover_mm)
    plus half of THIS closure bar's own diameter — a simple, single
    inset, not independently tuned per edge or tied to the main mat
    bars' own (possibly different) inset.

    Args:
        host                (DB.Element): the footing or floor.
        bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm (float):
                            SAME values already passed to
                            build_mat_bar_set(is_top=False) for this
                            host's bottom mat — used here purely to
                            re-derive B1/B2's own Z (Layer 1/Layer 2),
                            not to rebuild the bottom mat itself.
        top_cover_mm, top_dia_x_mm, top_dia_y_mm (float): SAME values
                            already passed to build_mat_bar_set
                            (is_top=True) for this host's top mat —
                            used here to re-derive T1/T2's own Z.
        x_anchor_dia_mm, x_anchor_spacing_mm (float): this closure
                            U-bar's own diameter/max-Set-spacing for
                            the two X-edges (anchoring B1/T1, the
                            along_x main bars).
        y_anchor_dia_mm, y_anchor_spacing_mm (float): same, for the two
                            Y-edges (anchoring B2/T2, the along_y main
                            bars).
        edge_cover_mm       (float or None): see DISCLOSED
                            SIMPLIFICATION above — defaults to
                            bottom_cover_mm.
        leg_length_mm       (float or None): see DISCLOSED
                            SIMPLIFICATION above — defaults to
                            default_anchorage_length_mm(that edge's own
                            diameter) per edge if not given.

    Returns:
        {
          'x_edges': [set_at_Xmin_or_None, set_at_Xmax_or_None],
          'y_edges': [set_at_Ymin_or_None, set_at_Ymax_or_None],
        }
        each set: {'curves': [DB.Curve,...], 'normal': DB.XYZ,
                   'array_length_mm': float, 'spacing_mm': float} — same
        shape as build_mat_bar_set's per-direction entries, ready for
        rebar_engine.RebarWrapper.create_rebar_set(). An entry is None
        if that edge is too short (after inset) to fit even one bar.

    Raises:
        ValueError: if the host's global bounding box can't be read, or
        if the bottom-to-top Z gap for either anchored pair (B1/T1 or
        B2/T2) is not positive (covers/diameters leave no room for the
        closure bar's own vertical back).
    """
    global_bbox = _footing_bbox(host)
    if global_bbox is None:
        raise ValueError(u'Could not read this host\'s global bounding box.')

    if edge_cover_mm is None:
        edge_cover_mm = bottom_cover_mm

    z_b1_ft = global_bbox.Min.Z + (bottom_cover_mm + bottom_dia_x_mm / 2.0) / _MM_PER_FT
    z_t1_ft = global_bbox.Max.Z - (top_cover_mm + top_dia_x_mm / 2.0) / _MM_PER_FT
    z_b2_ft = global_bbox.Min.Z + (bottom_cover_mm + bottom_dia_x_mm + bottom_dia_y_mm / 2.0) / _MM_PER_FT
    z_t2_ft = global_bbox.Max.Z - (top_cover_mm + top_dia_x_mm + top_dia_y_mm / 2.0) / _MM_PER_FT

    if z_t1_ft <= z_b1_ft:
        raise ValueError(u'No vertical gap between B1 and T1 for the X-edge '
                          u'perimeter closure U-bars — covers/diameters exceed '
                          u'this host\'s thickness.')
    if z_t2_ft <= z_b2_ft:
        raise ValueError(u'No vertical gap between B2 and T2 for the Y-edge '
                          u'perimeter closure U-bars — covers/diameters exceed '
                          u'this host\'s thickness.')

    def _one_edge_set(fixed_axis, edge_side, bottom_z_ft, top_z_ft,
                       bar_diameter_mm, spacing_mm):
        inset_ft = (edge_cover_mm + bar_diameter_mm / 2.0) / _MM_PER_FT
        leg_len_mm = (leg_length_mm if leg_length_mm is not None
                      else default_anchorage_length_mm(bar_diameter_mm))

        if fixed_axis == 'x':
            if edge_side == 'min':
                fixed_coord = global_bbox.Min.X + inset_ft
                leg_dir = DB.XYZ(1.0, 0.0, 0.0)
            else:
                fixed_coord = global_bbox.Max.X - inset_ft
                leg_dir = DB.XYZ(-1.0, 0.0, 0.0)
            span0 = global_bbox.Min.Y + inset_ft
            span1 = global_bbox.Max.Y - inset_ft
            if span1 <= span0:
                return None
            normal = DB.XYZ(0.0, 1.0, 0.0)

            def _curves_at(moving_ft):
                p_bottom = DB.XYZ(fixed_coord, moving_ft, bottom_z_ft)
                p_top = DB.XYZ(fixed_coord, moving_ft, top_z_ft)
                return add_end_hooks(DB.Line.CreateBound(p_bottom, p_top),
                                      leg_len_mm, leg_dir, at_start=True, at_end=True)
        else:
            if edge_side == 'min':
                fixed_coord = global_bbox.Min.Y + inset_ft
                leg_dir = DB.XYZ(0.0, 1.0, 0.0)
            else:
                fixed_coord = global_bbox.Max.Y - inset_ft
                leg_dir = DB.XYZ(0.0, -1.0, 0.0)
            span0 = global_bbox.Min.X + inset_ft
            span1 = global_bbox.Max.X - inset_ft
            if span1 <= span0:
                return None
            normal = DB.XYZ(1.0, 0.0, 0.0)

            def _curves_at(moving_ft):
                p_bottom = DB.XYZ(moving_ft, fixed_coord, bottom_z_ft)
                p_top = DB.XYZ(moving_ft, fixed_coord, top_z_ft)
                return add_end_hooks(DB.Line.CreateBound(p_bottom, p_top),
                                      leg_len_mm, leg_dir, at_start=True, at_end=True)

        # BUG FIX (2026-09-01) — this used to return a Set entry with NO
        # 'materialized_bars' key at all. ui.py's _create_grouped_bars
        # treats a missing/short materialized_bars list as "nothing to
        # fall back to" and gives up entirely (logs "(set) — {error}"
        # with no bars created) whenever create_rebar_set's own Set
        # propagation fails for this hook-bearing open shape — reported
        # live as "— None" with zero footing closure U-bars created.
        # Every individual position along the span is now materialized
        # up front, mirroring floor_rebar._build_edge_ubars' own
        # pattern for the identical hook/back/hook topology, so the
        # FreeForm-group (then individual-bar) fallback can actually run.
        positions_mm = _evenly_spaced(
            span0 * _MM_PER_FT, span1 * _MM_PER_FT, spacing_mm)
        positions_ft = [p / _MM_PER_FT for p in positions_mm]
        if not positions_ft:
            return None
        materialized = [{'curves': _curves_at(pos), 'normal': normal} for pos in positions_ft]
        return {
            'curves': materialized[0]['curves'],
            'normal': normal,
            'array_length_mm': (span1 - span0) * _MM_PER_FT,
            'spacing_mm': spacing_mm,
            'materialized_bars': materialized,
        }

    return {
        'x_edges': [
            _one_edge_set('x', 'min', z_b1_ft, z_t1_ft, x_anchor_dia_mm, x_anchor_spacing_mm),
            _one_edge_set('x', 'max', z_b1_ft, z_t1_ft, x_anchor_dia_mm, x_anchor_spacing_mm),
        ],
        'y_edges': [
            _one_edge_set('y', 'min', z_b2_ft, z_t2_ft, y_anchor_dia_mm, y_anchor_spacing_mm),
            _one_edge_set('y', 'max', z_b2_ft, z_t2_ft, y_anchor_dia_mm, y_anchor_spacing_mm),
        ],
    }


def build_side_rebar_set(doc, host, bottom_cover_mm, top_cover_mm, bar_diameter_mm, spacing_mm,
                         bottom_clear_mm=None, top_clear_mm=None, lateral_extra_mm=0.0):
    """
    A closed rectangular perimeter ("skin"/anti-crack) reinforcement
    shape, with its X/Y vertices sized from the BOTTOM face's own plan
    bounding box (inset by bottom_cover_mm + bar_diameter_mm/2 on all 4
    sides), placed at Z = the footing's GLOBAL bounding box Zmin +
    bottom_cover_mm, as ONE Rebar Set propagated VERTICALLY (+Z) up to
    Z = the footing's GLOBAL bounding box Zmax - top_cover_mm.

    PHASE 5.2 FIX — Z coordinates now come from host.get_BoundingBox(None)
    (the ELEMENT's own global, axis-aligned bounding box in document
    space), not from bottom_face.origin.Z / top_face.normal-offset
    arithmetic as Phase 5.1 did. Live testing showed the perimeter
    ending up below/outside the footing with the face-derived approach —
    host.get_BoundingBox(None) is the same, simpler, already-global API
    this module's create_rebar_detail_section uses successfully, and
    removes any dependency on get_host_solid()/get_footing_top_face()
    having picked exactly the right face for elevation purposes (only
    the BOTTOM face is still needed now, and only for X/Y). This
    directly matches the brief's own formula: "Z_min_global + bottom_cover"
    for the first loop, "Z_max_global - top_cover" for the top of the
    array.

    PHASE 5.2 FIX — propagation direction: `face_normal` in the
    returned dict is now DB.XYZ.BasisZ (straight up) instead of
    bottom_face.normal (which points DOWN). Passing a downward-pointing
    normal into RebarWrapper.create_rebar_set as the reference plane may
    be why the live test's propagated set ended up BELOW the first
    (correctly-placed) loop instead of above it — if
    ShapeDrivenAccessor's "normal side" propagates along +normal, an
    upward-pointing normal is what should make the set climb from the
    bottom loop toward the top one. Unverified beyond this reasoning —
    see rebar_engine.py's own note on this call's confidence.

    DISCLOSED SIMPLIFICATIONS (unchanged from Phase 5.1):
      - CLOSED rectangle, not a "U" shape.
      - Lateral cover reuses bottom_cover_mm (no separate side-cover
        input in the UI).
      - X/Y still come from the bottom face's own UV bounding box
        (assumed to equal the footing's plan footprint — this module's
        whole SCOPE) rather than the global AABB, since a rotated
        footing's global AABB would be LARGER than its true footprint
        and would place the perimeter wrong in the other direction; only
        Z switched to the global bbox, where rotation is not a concern
        for a footing whose top/bottom faces are horizontal.

    Args:
        doc               (DB.Document)
        host              (DB.Element): the footing.
        bottom_cover_mm   (float): bottom cover, mm — also used for the
                          perimeter's lateral inset and the array's
                          bottom elevation.
        top_cover_mm      (float): top cover, mm — used for the array's
                          top elevation only.
        bar_diameter_mm   (float): perimeter bar diameter, mm — used for
                          the lateral inset.
        spacing_mm        (float): maximum vertical spacing between
                          perimeter loops, mm.

    Returns:
        {'curves': list[DB.Line] (4, closed), 'array_length_mm': float,
         'spacing_mm': float, 'face_normal': DB.XYZ (straight up)}

    Raises:
        ValueError: if the host has no identifiable bottom face or no
        global bounding box, if the cover-inset plan area is too small
        to fit the perimeter, or if the resulting vertical array length
        is not positive (the top and bottom cover elevations don't leave
        any gap between them for this footing's actual depth).
    """
    engine = _ensure_engine()
    cover_mgr = engine.CoverGeometryManager(doc, host)
    bottom_face = get_footing_bottom_face(cover_mgr)
    if bottom_face is None:
        raise ValueError(u'Side rebar needs a clearly downward-facing bottom '
                          u'face on this footing.')

    global_bbox = _footing_bbox(host)
    if global_bbox is None:
        raise ValueError(u'Could not read this footing\'s global bounding box.')

    # lateral_extra_mm: inside the bent-up legs of the mats (IStructE SMDSC MF2 lacers)
    inset_ft = (bottom_cover_mm + lateral_extra_mm + bar_diameter_mm / 2.0) / _MM_PER_FT
    bbox = bottom_face.face.GetBoundingBox()
    u0, u1 = bbox.Min.U + inset_ft, bbox.Max.U - inset_ft
    v0, v1 = bbox.Min.V + inset_ft, bbox.Max.V - inset_ft
    if u1 <= u0 or v1 <= v0:
        raise ValueError(u'Footing is too small for side rebar at this cover/diameter.')

    # bottom/top_clear_mm: loop centreline to the bottom/top face, so the first and last loops sit
    # between the mats instead of in their plane (2026-10-02); default = the covers, as before
    bottom_z_ft = global_bbox.Min.Z + ((bottom_clear_mm or bottom_cover_mm) / _MM_PER_FT)
    top_z_ft = global_bbox.Max.Z - ((top_clear_mm or top_cover_mm) / _MM_PER_FT)
    array_length_ft = top_z_ft - bottom_z_ft
    if array_length_ft <= 0:
        raise ValueError(u'No vertical gap between the bottom and top cover '
                          u'elevations for side rebar — check the cover values '
                          u'against this footing\'s actual depth.')

    corners_uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    corner_pts = []
    for (u, v) in corners_uv:
        p = bottom_face.face.Evaluate(DB.UV(u, v))
        corner_pts.append(DB.XYZ(p.X, p.Y, bottom_z_ft))
    rectangle = [DB.Line.CreateBound(corner_pts[i], corner_pts[(i + 1) % 4]) for i in range(4)]

    return {
        'curves': rectangle,
        'array_length_mm': array_length_ft * _MM_PER_FT,
        'spacing_mm': spacing_mm,
        'face_normal': DB.XYZ.BasisZ,
    }


def _dowel_rect_positions(half_u_mm, half_v_mm, n_dowels):
    """(du, dv) offsets, mm: 4 corners, plus the 4 side midpoints when n_dowels is 8."""
    if n_dowels not in (4, 8):
        raise ValueError(u'Dowel count must be 4 or 8, got {}.'.format(n_dowels))
    positions = [(-half_u_mm, -half_v_mm), (half_u_mm, -half_v_mm),
                 (half_u_mm, half_v_mm), (-half_u_mm, half_v_mm)]
    if n_dowels == 8:
        positions += [(0.0, -half_v_mm), (half_u_mm, 0.0), (0.0, half_v_mm), (-half_u_mm, 0.0)]
    return positions


def _dowel_circle_positions(radius_mm, n_dowels):
    """(du, dv) offsets, mm: n_dowels evenly spaced on a circle, none on the axes' ends."""
    step = 2.0 * math.pi / n_dowels
    return [(radius_mm * math.cos(step * (i + 0.5)), radius_mm * math.sin(step * (i + 0.5)))
            for i in range(n_dowels)]


def build_dowel_curves(doc, host, cover_mm, n_dowels, anchor_length_mm,
                        splice_length_mm, bar_diameter_mm=16.0,
                        column_width_mm=400.0, column_depth_mm=400.0,
                        column_cover_mm=40.0, link_diameter_mm=10.0,
                        mat_dias_mm=None, column_bar_count=None, column_bar_dia_mm=None):
    """
    Vertical L-shaped dowels ("esperas") from this footing into the column(s) above.

    User decisions 2026-09-29 (T2.15/T2.15b): under each structural column
    whose base rests on this footing, one dowel per vertical the column will
    get with the Columns-tab values (column_bar_count / column_bar_dia_mm /
    link_diameter_mm and the column's own native cover), contact-lapped on
    the inner side of that vertical so the two never clash, foot pointing
    outwards. Without those values (or if they do not fit), n_dowels on the
    column's bar line instead. With no column above, one n_dowels cage
    centred on the footing with a column_width_mm x column_depth_mm section
    typed in the window — except on a strip footing (DB.WallFoundation),
    which gets none: its wall brings its own starters. Dowels rest on the bottom mat and rise
    splice_length_mm above the footing's own top. Columns that already have
    NOSA dowels or foundation starters rising through them are skipped, so
    arming the footing and the column never duplicates bars.

    Returns:
        {'bars': list[DB.Line], 'normals': list[DB.XYZ], 'embedded_mm': float,
         'anchor_length_mm': float, 'columns': int, 'skipped_columns': list[int]}
    """
    engine = _ensure_engine()
    own = engine.get_isolated_solid_bbox(host) or host.get_BoundingBox(None)
    # Foot rests on the bottom mat (T2.16): mat_dias_mm = this run's X/Y mat bars.
    bottom_z_ft, _ = engine.starter_foot_z(doc, host, own, cover_mm, bar_diameter_mm, mat_dias_mm)
    top_z_ft = own.Max.Z + splice_length_mm / _MM_PER_FT
    inset_mm = column_cover_mm + link_diameter_mm + bar_diameter_mm / 2.0 +         engine.link_corner_extra_inset_mm(bar_diameter_mm, link_diameter_mm)

    cages = []
    contact = []
    groups = []
    skipped_columns = []
    fallback_columns = []
    columns = engine.find_columns_above(doc, host)
    for column in columns:
        if engine.nosa_bars_in_footprint(doc, column, (u'dowel', u'foundation_starter')):
            skipped_columns.append(column.Id)
            continue
        if column_bar_count and column_bar_dia_mm:
            try:
                col_cover_mm = engine.get_native_cover_mm(doc, column, u'Exterior', column_cover_mm)
                layout = _ensure_column_rebar().column_vertical_plan_layout(
                    doc, column, col_cover_mm, column_bar_dia_mm, column_bar_count, link_diameter_mm)
                lap_ft = (column_bar_dia_mm + bar_diameter_mm) / 2.0 / _MM_PER_FT
                points = [p + d.Multiply(lap_ft) for p, d in zip(layout['points'], layout['inward'])]
                outward = [d.Negate() for d in layout['inward']]
                try:
                    col_hand = DB.XYZ(column.HandOrientation.X, column.HandOrientation.Y, 0.0).Normalize()
                except Exception:
                    col_hand = DB.XYZ.BasisX
                contact.append((points, outward, col_hand))
                continue
            except Exception:
                fallback_columns.append(column.Id)
        bbox = column.get_BoundingBox(None)
        centre = DB.XYZ((bbox.Min.X + bbox.Max.X) / 2.0, (bbox.Min.Y + bbox.Max.Y) / 2.0, 0.0)
        try:
            hand = DB.XYZ(column.HandOrientation.X, column.HandOrientation.Y, 0.0).Normalize()
            facing = DB.XYZ(column.FacingOrientation.X, column.FacingOrientation.Y, 0.0).Normalize()
        except Exception:
            hand, facing = DB.XYZ.BasisX, DB.XYZ.BasisY
        geom = _ensure_column_rebar().detect_column_geometry(doc, column)
        if geom is not None and geom.get('shape') == 'circle':
            offsets = _dowel_circle_positions(geom['diameter_mm'] / 2.0 - inset_mm, n_dowels)
        else:
            width_mm = geom['width_mm'] if geom else (bbox.Max.X - bbox.Min.X) * _MM_PER_FT
            depth_mm = geom['depth_mm'] if geom else (bbox.Max.Y - bbox.Min.Y) * _MM_PER_FT
            offsets = _dowel_rect_positions(width_mm / 2.0 - inset_mm, depth_mm / 2.0 - inset_mm, n_dowels)
        cages.append((centre, hand, facing, offsets))

    wall_footing = not columns and isinstance(host, DB.WallFoundation)
    if not columns and not wall_footing:
        centre = DB.XYZ((own.Min.X + own.Max.X) / 2.0, (own.Min.Y + own.Max.Y) / 2.0, 0.0)
        offsets = _dowel_rect_positions(column_width_mm / 2.0 - inset_mm,
                                        column_depth_mm / 2.0 - inset_mm, n_dowels)
        cages.append((centre, DB.XYZ.BasisX, DB.XYZ.BasisY, offsets))

    bars = []
    normals = []
    for centre, hand, facing, offsets in cages:
        first = len(bars)
        for du_mm, dv_mm in offsets:
            p = centre + hand.Multiply(du_mm / _MM_PER_FT) + facing.Multiply(dv_mm / _MM_PER_FT)
            bars.append(DB.Line.CreateBound(DB.XYZ(p.X, p.Y, bottom_z_ft), DB.XYZ(p.X, p.Y, top_z_ft)))
            normals.append(engine.starter_hook_plane_normal(DB.XYZ(p.X - centre.X, p.Y - centre.Y, 0.0)))
        groups.append({'bars': bars[first:], 'hand': hand})
    for points, outward, col_hand in contact:
        first = len(bars)
        for p, hook_dir in zip(points, outward):
            bars.append(DB.Line.CreateBound(DB.XYZ(p.X, p.Y, bottom_z_ft), DB.XYZ(p.X, p.Y, top_z_ft)))
            normals.append(engine.starter_hook_plane_normal(hook_dir))
        groups.append({'bars': bars[first:], 'hand': col_hand})

    return {'bars': bars, 'normals': normals, 'groups': groups,
            'embedded_mm': (own.Max.Z - bottom_z_ft) * _MM_PER_FT,
            'anchor_length_mm': anchor_length_mm,
            'columns': len(columns), 'skipped_columns': skipped_columns,
            'fallback_columns': fallback_columns, 'wall_footing': wall_footing}


# ══════════════════════════════════════════════════════════════════════════
# PHASE 3.5.7 item 3 — real topology (holes) for the main mat + closure
# U-bars, replacing build_mat_bar_set/build_perimeter_closure_ubar_sets'
# host.get_BoundingBox(None)-only rectangular assumption. Full port of
# floor_rebar.py's Phase 2.2+ approach: extract the REAL boundary loops
# from the footing's own bottom/top face (slab_topology), clip the main
# grid through any interior opening (large hole), and walk the real
# polygon edge-by-edge for perimeter closure U-bars — including hole
# edges — reusing floor_rebar.py's own tested _build_direction_bars /
# _build_edge_ubars directly rather than re-deriving the same logic.
# build_mat_bar_set / build_perimeter_closure_ubar_sets themselves are
# left INTACT below (build_side_rebar_set / build_dowel_curves still
# use the plain bbox, out of this fix's scope) — not deleted, since a
# footing with genuinely no solid/face geometry readable would still
# need SOME fallback; build_footing_reinforcement below now calls the
# topology versions as primary.
# ══════════════════════════════════════════════════════════════════════════

def pile_centres_ft(host, tol_mm=10.0):
    """Plan centres (x, y) of the piles nested in a pile-cap family: nested solids under the cap's own body."""
    engine = _ensure_engine()
    own = engine.get_isolated_solid_bbox(host)
    if own is None:
        return []
    centres = []
    try:      # shared nested piles: their own elements, reaching below the cap
        for sid in host.GetSubComponentIds():
            box = host.Document.GetElement(sid).get_BoundingBox(None)
            if box is not None and box.Min.Z < own.Min.Z - tol_mm / _MM_PER_FT:
                centres.append(((box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0))
    except Exception:
        centres = []
    if centres:
        return centres
    try:
        geometry = host.get_Geometry(DB.Options())
    except Exception:
        return []
    def _solids(items):
        for obj in items or []:
            if isinstance(obj, DB.GeometryInstance):
                for sub in _solids(obj.GetInstanceGeometry()):
                    yield sub
            elif isinstance(obj, DB.Solid) and obj.Volume > 0.0:
                yield obj

    for sub in _solids(geometry):
        pts = [p for edge in sub.Edges for p in edge.Tessellate()]
        if not pts or min(p.Z for p in pts) > own.Min.Z - tol_mm / _MM_PER_FT:
            continue                         # not reaching below the cap: the cap itself
        x = (min(p.X for p in pts) + max(p.X for p in pts)) / 2.0
        y = (min(p.Y for p in pts) + max(p.Y for p in pts)) / 2.0
        if all(abs(x - a) > 1e-3 or abs(y - b) > 1e-3 for a, b in centres):
            centres.append((x, y))
    return centres


def pile_cap_anchorage_notes(host, side_cover_mm, cover_mm, top_cover_mm, dia_x_mm, dia_y_mm,
                             anchorage_x_mm, anchorage_y_mm):
    """
    IStructE SMDSC 6.7 / MF2: a full tension anchorage from the centre line of the edge pile to the end
    of the bar (along the mat, then up the bent end). Notes where the cap is too small for it.
    """
    engine = _ensure_engine()
    own = engine.get_isolated_solid_bbox(host)
    piles = pile_centres_ft(host)
    if own is None or not piles:
        return []
    height_mm = (own.Max.Z - own.Min.Z) * _MM_PER_FT
    leg_mm = height_mm - cover_mm - (top_cover_mm or cover_mm)
    notes = []
    for axis, k, dia, need in ((u'X', 0, dia_x_mm, anchorage_x_mm), (u'Y', 1, dia_y_mm, anchorage_y_mm)):
        lo, hi = (own.Min.X, own.Max.X) if k == 0 else (own.Min.Y, own.Max.Y)
        pmin, pmax = min(p[k] for p in piles), max(p[k] for p in piles)
        reach = min(pmin - lo, hi - pmax) * _MM_PER_FT - side_cover_mm - dia / 2.0
        have = reach + leg_mm
        if have < need - 1.0:
            notes.append(u'pile cap {} bars: {:.0f} mm from the edge pile centre to the bar end, under the '
                         u'{:.0f} mm tension anchorage SMDSC MF2 asks for — larger bends or a bigger cap.'.format(
                             axis, have, need))
    return notes


def _plan_extent_ft(bbox, direction):
    """(min, max) of a bounding box's plan corners along a horizontal direction, ft."""
    values = [DB.XYZ(x, y, 0.0).DotProduct(direction)
              for x in (bbox.Min.X, bbox.Max.X) for y in (bbox.Min.Y, bbox.Max.Y)]
    return min(values), max(values)


def apply_column_band(doc, host, mat, cover_mm, dia_x_mm, dia_y_mm, max_pitch_mm=300.0):
    """
    IStructE SMDSC 6.7: where a footing is longer than 1.5 (c + 3d) across a mat direction, two thirds
    of that direction's bars go in a band c + 3d wide centred on the column, the rest in the outer
    strips (at most max_pitch apart). Only for one column on a plain rectangular mat (one Set per
    direction); the mat dict is changed in place and a note added.
    """
    from nosa_utils import mesh_rules
    from nosa_utils.revit_helpers import get_id_value
    engine = _ensure_engine()
    columns = engine.find_columns_above(doc, host)
    own = engine.get_isolated_solid_bbox(host) or host.get_BoundingBox(None)
    if len(columns) != 1 or own is None:
        return
    column_box = columns[0].get_BoundingBox(None)
    if column_box is None:
        return
    thickness_mm = (own.Max.Z - own.Min.Z) * _MM_PER_FT
    for key, dia_mm in (('along_x', dia_x_mm), ('along_y', dia_y_mm)):
        grouped = mat.get(key) or {}
        sets = grouped.get('sets') or []
        if len(sets) != 1 or grouped.get('bars'):
            continue
        st = sets[0]
        spacing_mm, length_mm = st.get('spacing_mm') or 0.0, st.get('array_length_mm') or 0.0
        if spacing_mm <= 0.0 or length_mm <= 0.0:
            continue
        n = DB.XYZ(st['normal'].X, st['normal'].Y, 0.0)
        if n.GetLength() < 1e-9:
            continue
        n = n.Normalize()
        count = int(math.ceil(length_mm / spacing_mm - 1e-6)) + 1
        start = st['curves'][0].GetEndPoint(0)
        lo = DB.XYZ(start.X, start.Y, 0.0).DotProduct(n) * _MM_PER_FT
        f0, f1 = _plan_extent_ft(own, n)
        c0, c1 = _plan_extent_ft(column_box, n)
        d_mm = thickness_mm - cover_mm - dia_mm
        band = mesh_rules.footing_band_mm((f1 - f0) * _MM_PER_FT, (c1 - c0) * _MM_PER_FT, d_mm)
        if band is None:
            continue
        centre = (c0 + c1) / 2.0 * _MM_PER_FT
        layout = mesh_rules.band_layout_mm(lo, lo + length_mm, count, centre - band / 2.0,
                                           centre + band / 2.0, max_pitch_mm)
        notes = grouped.setdefault('notes', [])
        if layout is None:
            notes.append(u'Footing {}: SMDSC 6.7 asks for two thirds of the {} bars in a {:.0f} mm band '
                         u'under the column: at this bar count they would be closer than 100 mm. Use a larger bar '
                         u'size or detail the band by hand.'.format(get_id_value(host.Id), key.replace(u'_', u' '), band))
            continue
        new_sets, new_bars = [], []
        for run in layout:
            if not run:
                continue
            shift = DB.Transform.CreateTranslation(n.Multiply((run[0] - lo) / _MM_PER_FT))
            curves = [c.CreateTransformed(shift) for c in st['curves']]
            if len(run) == 1:
                new_bars.append({'curves': curves, 'normal': st['normal']})
                continue
            piece = dict((k, v) for k, v in st.items() if k != 'materialized_bars')
            piece.update({'curves': curves, 'spacing_mm': (run[1] - run[0]) + 0.01,
                          'array_length_mm': run[-1] - run[0]})
            new_sets.append(piece)
        grouped['sets'], grouped['bars'] = new_sets, new_bars
        notes.append(u'Footing {}: {} of {} {} bars in a {:.0f} mm band under the column '
                     u'(SMDSC 6.7: footing {:.0f} mm > 1.5 (c + 3d)).'.format(
                         get_id_value(host.Id), len(layout[0]), sum(len(r) for r in layout),
                         key.replace(u'_', u' '), band, (f1 - f0) * _MM_PER_FT))


def build_mat_bars_topology(doc, host, is_top, cover_mm, dia_x_mm, dia_y_mm,
                             spacing_x_mm, spacing_y_mm, max_stock_length_mm=12000.0,
                             target_z_mm=None, leg_direction=None):
    """
    PHASE 3.5.7 item 3 — topology-aware counterpart of build_mat_bar_set:
    same Z-layering convention (along_x = Layer 1, along_y = Layer 2 —
    see build_mat_bar_set's own docstring for the exact formulas, kept
    identical here) and the same full-depth-leg ("hooks") support via
    target_z_mm/leg_direction, but the X/Y extent and any interior
    openings now come from the footing's REAL bottom-face boundary
    (slab_topology.extract_loops_mm/classify_loops/offset_polygon_mm),
    with each row's bars clipped through every large hole via
    floor_rebar._build_direction_bars — the exact mechanism floors
    already use, reused directly rather than re-implemented.

    Args: same meaning as build_mat_bar_set's own parameters of the
    identical name, plus:
        doc                  (DB.Document)
        max_stock_length_mm  (float): commercial bar length for
                             splitting a row longer than stock — see
                             floor_rebar._build_direction_bars'
                             own use (via rebar_engine.
                             split_rebar_by_stock_length).

    Returns:
        {'along_x': {'sets':[...], 'bars':[...]},
         'along_y': {'sets':[...], 'bars':[...]}}
        — SAME shape as floor_rebar.build_floor_reinforcement's own
        'along_x'/'along_y' entries, consumed by ui.py's
        _create_grouped_bars (the same method floors already use) —
        NOT build_mat_bar_set's single-Set-per-direction shape, since a
        hole-clipped row can no longer be represented as one uniform
        Set spanning the whole footing.

    Raises:
        ValueError: if no clearly downward/upward-facing (as
        applicable) face can be found on this footing.
    """
    engine = _ensure_engine()
    topo = _ensure_topology()
    floor_mod = _ensure_floor_rebar()
    cover_mgr = engine.CoverGeometryManager(doc, host)

    face_info = get_footing_top_face(cover_mgr) if is_top else get_footing_bottom_face(cover_mgr)
    if face_info is None:
        raise ValueError(
            u'Could not find a clearly {}-facing face on this footing.'.format(
                u'upward' if is_top else u'downward'))

    raw_loops = topo.extract_loops_mm(face_info.face)
    raw_outer, raw_holes, _n_small = topo.classify_loops(raw_loops)
    outer = topo.offset_polygon_mm(raw_outer, cover_mm)
    large_holes = [topo.offset_polygon_mm(h, -cover_mm) for h in raw_holes]
    xmin_mm, xmax_mm, ymin_mm, ymax_mm = topo.polygon_bbox_mm(outer)

    face_z_ft = face_info.origin.Z
    if is_top:
        z_layer1_ft = face_z_ft - (cover_mm + dia_x_mm / 2.0) / _MM_PER_FT
        z_layer2_ft = face_z_ft - (cover_mm + dia_x_mm + dia_y_mm / 2.0) / _MM_PER_FT
    else:
        z_layer1_ft = face_z_ft + (cover_mm + dia_x_mm / 2.0) / _MM_PER_FT
        z_layer2_ft = face_z_ft + (cover_mm + dia_x_mm + dia_y_mm / 2.0) / _MM_PER_FT

    use_legs = target_z_mm is not None and leg_direction is not None
    leg1_mm = abs(target_z_mm - z_layer1_ft * _MM_PER_FT) if use_legs else 0.0
    leg2_mm = abs(target_z_mm - z_layer2_ft * _MM_PER_FT) if use_legs else 0.0

    along_x = floor_mod._build_direction_bars(
        topo, sys.modules[__name__], engine, DB, outer, large_holes, 'x',
        dia_x_mm, dia_y_mm, spacing_y_mm,
        xmin_mm, xmax_mm, ymin_mm, ymax_mm, z_layer1_ft, max_stock_length_mm,
        use_legs=use_legs, leg_length_mm=leg1_mm, leg_direction=leg_direction)
    along_y = floor_mod._build_direction_bars(
        topo, sys.modules[__name__], engine, DB, outer, large_holes, 'y',
        dia_y_mm, dia_x_mm, spacing_x_mm,
        xmin_mm, xmax_mm, ymin_mm, ymax_mm, z_layer2_ft, max_stock_length_mm,
        use_legs=use_legs, leg_length_mm=leg2_mm, leg_direction=leg_direction)

    return {'along_x': along_x, 'along_y': along_y}


def build_perimeter_closure_ubars_topology(doc, host,
                                            bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
                                            top_cover_mm, top_dia_x_mm, top_dia_y_mm,
                                            x_anchor_dia_mm, x_anchor_spacing_mm,
                                            y_anchor_dia_mm, y_anchor_spacing_mm,
                                            std=None, bottom_spacing_mm=None):
    """
    PHASE 3.5.7 item 3 — topology-aware counterpart of
    build_perimeter_closure_ubar_sets: walks the footing's REAL
    boundary edge-by-edge (outer boundary AND every large interior
    opening) via floor_rebar._build_edge_ubars, the exact mechanism
    floors already use, instead of assuming 4 straight rectangular
    edges. A hole in a footing/pile cap now gets its own perimeter
    closure U-bars around it, same as the outer boundary.

    Args: same meaning as build_perimeter_closure_ubar_sets's own
    parameters of the identical name (edge_cover_mm/leg_length_mm
    overrides are NOT supported here — always the default anchorage
    length per this closure bar's own diameter, matching floor_rebar's
    own convention).

    Returns:
        {'x_bars': {'sets':[...], 'bars':[...]},
         'y_bars': {'sets':[...], 'bars':[...]},
         'debug_failed_edges': [...]}
        — SAME shape as floor_rebar.build_floor_reinforcement's own
        'perimeter_closure_ubars', consumed by ui.py's
        _create_grouped_bars per direction.

    Raises:
        ValueError: if no clearly downward/upward-facing face can be
        found on this footing.
    """
    engine = _ensure_engine()
    topo = _ensure_topology()
    floor_mod = _ensure_floor_rebar()
    cover_mgr = engine.CoverGeometryManager(doc, host)

    bottom_face = get_footing_bottom_face(cover_mgr)
    if bottom_face is None:
        raise ValueError(u'Could not find a clearly downward-facing bottom face '
                          u'on this footing.')
    top_face = get_footing_top_face(cover_mgr)
    if top_face is None:
        raise ValueError(u'Could not find a clearly upward-facing top face on '
                          u'this footing.')

    raw_loops = topo.extract_loops_mm(bottom_face.face)
    raw_outer, raw_holes, _n_small = topo.classify_loops(raw_loops)
    bottom_outer = topo.offset_polygon_mm(raw_outer, bottom_cover_mm)
    bottom_holes = [topo.offset_polygon_mm(h, -bottom_cover_mm) for h in raw_holes]

    bottom_z_ft = bottom_face.origin.Z
    top_z_ft = top_face.origin.Z
    # Same centrelines as the mats they close (T2.10b).
    b1_z_ft = bottom_z_ft + (bottom_cover_mm + bottom_dia_x_mm / 2.0) / _MM_PER_FT
    b2_z_ft = bottom_z_ft + (bottom_cover_mm + bottom_dia_x_mm + bottom_dia_y_mm / 2.0) / _MM_PER_FT
    t1_z_ft = top_z_ft - (top_cover_mm + top_dia_x_mm / 2.0) / _MM_PER_FT
    t2_z_ft = top_z_ft - (top_cover_mm + top_dia_x_mm + top_dia_y_mm / 2.0) / _MM_PER_FT

    # PHASE F2.5 — a closure U-bar's leg is a "good bond, tension" anchorage
    # into the opposite mat (not a lap, not compression) — matches
    # default_anchorage_length_mm's own defaults (good_bond=True,
    # in_compression=False), just now sourced from `std` when resolved.
    # Edge U-bar legs lap with the mat bars: a full lap, every bar at one section.
    good = good_bond_for_top_bars((top_z_ft - bottom_z_ft) * _MM_PER_FT)
    x_leg_mm = default_lap_mm(x_anchor_dia_mm, std=std, good_bond=good)
    y_leg_mm = default_lap_mm(y_anchor_dia_mm, std=std, good_bond=good)

    # T2.17: one U-bar beside each bottom-mat bar, over the mat's whole zone.
    rows = None
    if bottom_spacing_mm:
        xmin_mm, xmax_mm, ymin_mm, ymax_mm = topo.polygon_bbox_mm(bottom_outer)
        rows = floor_mod.mat_rows_mm(xmin_mm, xmax_mm, ymin_mm, ymax_mm,
                                     bottom_dia_x_mm, bottom_dia_y_mm, bottom_spacing_mm,
                                     sys.modules[__name__])
        rows.update({'x_dia_mm': bottom_dia_x_mm, 'y_dia_mm': bottom_dia_y_mm,
                     'x_ubar_dia_mm': x_anchor_dia_mm, 'y_ubar_dia_mm': y_anchor_dia_mm})
    # U-bar back centreline at cover + radius (see floor_rebar's closure call).
    ubar_inset_mm = bottom_cover_mm + max(x_anchor_dia_mm, y_anchor_dia_mm) / 2.0
    ubar_outer = topo.offset_polygon_mm(raw_outer, ubar_inset_mm)
    ubar_holes = [topo.offset_polygon_mm(h, -ubar_inset_mm) for h in raw_holes]
    return floor_mod._build_edge_ubars(
        topo, sys.modules[__name__], DB, ubar_outer, ubar_holes,
        x_leg_mm, x_anchor_spacing_mm, b1_z_ft, t1_z_ft,
        y_leg_mm, y_anchor_spacing_mm, b2_z_ft, t2_z_ft, mat_rows=rows)


def build_footing_reinforcement(doc, host,
                                 bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
                                 bottom_spacing_mm, bottom_hooks=False,
                                 include_top_mat=False, top_cover_mm=None,
                                 top_dia_x_mm=None, top_dia_y_mm=None,
                                 top_spacing_mm=None, top_hooks=False,
                                 include_dowels=False, dowel_count=4,
                                 dowel_diameter_mm=16.0, dowel_anchor_length_mm=400.0,
                                 dowel_splice_length_mm=600.0,
                                 dowel_column_width_mm=400.0, dowel_column_depth_mm=400.0,
                                 dowel_column_bar_count=None, dowel_column_bar_dia_mm=None,
                                 dowel_column_link_dia_mm=10.0,
                                 include_side_rebar=False, side_diameter_mm=None,
                                 side_spacing_mm=None,
                                 include_perimeter_closure_ubars=False,
                                 x_anchor_ubar_dia_mm=None, x_anchor_ubar_spacing_mm=None,
                                 y_anchor_ubar_dia_mm=None, y_anchor_ubar_spacing_mm=None,
                                 max_stock_length_mm=12000.0, std=None):
    """
    Full pipeline for one footing host: bottom mat (always), optional
    top mat, optional dowel cage, optional side/skin reinforcement.
    This is the advanced-detailing entry point ui.py's "ARMADO
    AUTOMÁTICO DE ZAPATAS" button calls.

    PHASE 5.5 — bottom_mat/top_mat now come from build_mat_bar_set() (ONE
    U-bar shape + array_length per direction, for a Rebar Set — MRA/
    schedule-friendly) instead of Phase 5.4's build_mat_bar_chains() (a
    LIST of individually-instantiated U-bars) — see build_mat_bar_set()'s
    docstring for why (Multi-Rebar Annotation and quantity take-off both
    need one countable Set, not N loose elements).
    build_mat_bar_chains() is left fully INTACT below — Phase 5.4's
    live test confirmed it genuinely works, it just isn't what a
    production deliverable needs, so it remains available as a fallback
    if Sets turn out not to work for a given model after all.

    PHASE 5.6 — bottom_dia_x_mm/bottom_dia_y_mm (and top_*) are no
    longer collapsed into a single max()-based inset diameter: each
    direction now gets its OWN edge inset AND its OWN role in the
    Z-layering scheme (see build_mat_bar_set()'s docstring — 'along_x'
    is always Layer 1, 'along_y' is always Layer 2) — Phase 5.5's
    "mixed X/Y diameters" DISCLOSED SIMPLIFICATION no longer applies.

    bottom_hooks/top_hooks still mean "give this mat's bars full-depth
    U-bar legs reaching the OPPOSITE mat" (Phase 5.4's RC-detailing
    convention, unchanged) — but the target elevation each layer's legs
    reach is now computed from the host's GLOBAL bounding box directly
    (z_max_mm - effective_top_cover_mm for the bottom mat's legs,
    z_min_mm + bottom_cover_mm for the top mat's) and handed to
    build_mat_bar_set() as `target_z_mm`, which derives each layer's OWN
    leg length from ITS OWN (slightly different, Z-layered) starting
    elevation — see that function's docstring. If include_top_mat is
    False, top_cover_mm isn't available, so bottom_cover_mm is reused
    as a DISCLOSED SIMPLIFICATION (assumes symmetric cover) purely to
    give the bottom mat's legs a sensible target even without a
    physical top mat present.

    Args:
        doc                 (DB.Document)
        host                (DB.Element): the footing.
        bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
        bottom_spacing_mm   (float): bottom mat parameters — dia_x_mm is
                            Layer 1's diameter, dia_y_mm is Layer 2's
                            (see build_mat_bar_set's Z-layering).
        bottom_hooks        (bool): whether the bottom mat's bars get
                            full-depth U-bar legs reaching up toward the
                            top mat (see above).
        include_top_mat     (bool): whether to also build a top mat.
        top_cover_mm, top_dia_x_mm, top_dia_y_mm, top_spacing_mm
                            (float or None): required if
                            include_top_mat is True, ignored otherwise.
        top_hooks           (bool): like bottom_hooks, for the top mat
                            (legs reach DOWN toward the bottom mat).
        include_dowels      (bool): whether to also build a dowel cage.
        dowel_count         (int): 4 or 8 — see
                            build_dowel_curves/_dowel_square_positions.
        dowel_diameter_mm, dowel_anchor_length_mm,
        dowel_splice_length_mm (float): see build_dowel_curves.
        include_side_rebar   (bool): whether to also build perimeter
                            side/skin reinforcement.
        side_diameter_mm, side_spacing_mm (float or None): required if
                            include_side_rebar is True — see
                            build_side_rebar_set (which reuses
                            bottom_cover_mm/top_cover_mm — see its own
                            docstring's DISCLOSED SIMPLIFICATIONS).

        include_perimeter_closure_ubars (bool): whether to also build
                            the Phase 2.1 perimeter closure U-bars (see
                            build_perimeter_closure_ubar_sets) — REQUIRES
                            include_top_mat=True (the closure bars' backs
                            span bottom-mat Z to top-mat Z; there is no
                            top mat to anchor to otherwise).
        x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm,
        y_anchor_ubar_dia_mm, y_anchor_ubar_spacing_mm (float or None):
                            required if include_perimeter_closure_ubars
                            is True — see build_perimeter_closure_ubar_sets.
        std                 (dict or None): PHASE F2.5 — a resolved
                            nosa_utils.standards profile. Only affects
                            the perimeter closure U-bars' anchorage leg
                            length today (build_perimeter_closure_ubars_
                            topology's own default_anchorage_length_mm
                            call) — dowel anchor/splice length are always
                            explicit UI values (ui.py never omits them),
                            so std has nothing to default there yet.
                            Omitting std (the default, None) reproduces
                            exactly this function's pre-F2.5 behaviour.

    Returns:
        {
          'bottom_mat': build_mat_bars_topology()'s return shape
                        ('along_x'/'along_y', each {'sets':[...],'bars':[...]},
                        Layer 1/Layer 2 — Phase 3.5.7 item 3, real
                        topology/holes, consumed via ui.py's
                        _create_grouped_bars),
          'top_mat':    same shape, or None,
          'dowels':     {'bars': [...], 'face_normal': DB.XYZ}, or None,
          'side_rebar': build_side_rebar_set()'s return shape, or None,
          'perimeter_closure_ubars': build_perimeter_closure_ubars_topology()'s
                        return shape ({'x_bars','y_bars','debug_failed_edges'}),
                        or None,
        }

    Raises:
        ValueError: from get_footing_bottom_face / get_footing_top_face
        / build_mat_bar_set / build_dowel_curves / build_side_rebar_set
        / build_perimeter_closure_ubar_sets, if include_top_mat /
        include_side_rebar / include_perimeter_closure_ubars is True but
        any of their required arguments is None, if
        include_perimeter_closure_ubars is True but include_top_mat is
        False, or if (bottom_hooks or top_hooks) is True but the
        resulting leg target leaves no positive usable height (covers/
        diameters exceed the footing's thickness).
    """
    engine = _ensure_engine()
    cover_mgr = engine.CoverGeometryManager(doc, host)

    bottom_face = get_footing_bottom_face(cover_mgr)
    if bottom_face is None:
        raise ValueError(
            u'Could not find a clearly downward-facing bottom face on this '
            u'footing — is it flat-soffit? Sloped/stepped footings are not '
            u'supported by this module yet.')

    global_bbox = _footing_bbox(host)
    if global_bbox is None:
        raise ValueError(u'Could not read this footing\'s global bounding box.')
    z_min_mm = global_bbox.Min.Z * _MM_PER_FT
    z_max_mm = global_bbox.Max.Z * _MM_PER_FT
    effective_top_cover_mm = top_cover_mm if include_top_mat else bottom_cover_mm

    bottom_target_z_mm = None
    if bottom_hooks:
        bottom_target_z_mm = z_max_mm - effective_top_cover_mm
        if bottom_target_z_mm <= z_min_mm + bottom_cover_mm:
            raise ValueError(u'No usable internal height for the bottom mat\'s '
                              u'full-depth U-bar legs — covers exceed this '
                              u'footing\'s thickness.')

    bottom_mat = build_mat_bars_topology(
        doc, host, is_top=False, cover_mm=bottom_cover_mm,
        dia_x_mm=bottom_dia_x_mm, dia_y_mm=bottom_dia_y_mm,
        spacing_x_mm=bottom_spacing_mm, spacing_y_mm=bottom_spacing_mm,
        max_stock_length_mm=max_stock_length_mm,
        target_z_mm=bottom_target_z_mm,
        leg_direction=DB.XYZ.BasisZ if bottom_hooks else None)

    apply_column_band(doc, host, bottom_mat, bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm)

    result = {'bottom_mat': bottom_mat, 'top_mat': None, 'dowels': None, 'side_rebar': None,
              'perimeter_closure_ubars': None}

    if include_top_mat:
        if None in (top_cover_mm, top_dia_x_mm, top_dia_y_mm, top_spacing_mm):
            raise ValueError(u'include_top_mat requires top_cover_mm, top_dia_x_mm, '
                              u'top_dia_y_mm and top_spacing_mm to all be given.')
        top_face = get_footing_top_face(cover_mgr)
        if top_face is None:
            raise ValueError(u'Include Top Mat was requested but no clearly '
                              u'upward-facing top face was found on this footing.')

        top_target_z_mm = None
        if top_hooks:
            top_target_z_mm = z_min_mm + bottom_cover_mm
            if top_target_z_mm >= z_max_mm - top_cover_mm:
                raise ValueError(u'No usable internal height for the top mat\'s '
                                  u'full-depth U-bar legs — covers exceed this '
                                  u'footing\'s thickness.')

        top_mat = build_mat_bars_topology(
            doc, host, is_top=True, cover_mm=top_cover_mm,
            dia_x_mm=top_dia_x_mm, dia_y_mm=top_dia_y_mm,
            spacing_x_mm=top_spacing_mm, spacing_y_mm=top_spacing_mm,
            max_stock_length_mm=max_stock_length_mm,
            target_z_mm=top_target_z_mm,
            leg_direction=DB.XYZ.BasisZ.Multiply(-1.0) if top_hooks else None)
        result['top_mat'] = top_mat

    if include_dowels:
        result['dowels'] = build_dowel_curves(
            doc, host, bottom_cover_mm, dowel_count, dowel_anchor_length_mm,
            dowel_splice_length_mm, bar_diameter_mm=dowel_diameter_mm,
            column_width_mm=dowel_column_width_mm, column_depth_mm=dowel_column_depth_mm,
            mat_dias_mm=(bottom_dia_x_mm, bottom_dia_y_mm),
            link_diameter_mm=dowel_column_link_dia_mm or 10.0,
            column_bar_count=dowel_column_bar_count, column_bar_dia_mm=dowel_column_bar_dia_mm)

    if include_side_rebar:
        if None in (side_diameter_mm, side_spacing_mm):
            raise ValueError(u'include_side_rebar requires side_diameter_mm and '
                              u'side_spacing_mm to both be given.')
        effective_top_cover_mm = top_cover_mm if include_top_mat else bottom_cover_mm
        half_side = side_diameter_mm / 2.0
        bottom_clear = bottom_cover_mm + bottom_dia_x_mm + bottom_dia_y_mm + half_side
        top_clear = (top_cover_mm + (top_dia_x_mm or 0.0) + (top_dia_y_mm or 0.0) + half_side
                     if include_top_mat else bottom_cover_mm + half_side)
        result['side_rebar'] = build_side_rebar_set(
            doc, host, bottom_cover_mm, effective_top_cover_mm, side_diameter_mm, side_spacing_mm,
            bottom_clear_mm=bottom_clear, top_clear_mm=top_clear,
            lateral_extra_mm=max(bottom_dia_x_mm, bottom_dia_y_mm) if bottom_hooks else 0.0)

    if include_perimeter_closure_ubars:
        if not include_top_mat:
            raise ValueError(u'Perimeter Closure U-Bars require Include Top '
                              u'Reinforcement Mat to also be checked — the closure '
                              u'bars anchor between the bottom and top mats.')
        if None in (x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm,
                    y_anchor_ubar_dia_mm, y_anchor_ubar_spacing_mm):
            raise ValueError(u'include_perimeter_closure_ubars requires '
                              u'x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm, '
                              u'y_anchor_ubar_dia_mm and y_anchor_ubar_spacing_mm '
                              u'to all be given.')
        result['perimeter_closure_ubars'] = build_perimeter_closure_ubars_topology(
            doc, host, bottom_cover_mm, bottom_dia_x_mm, bottom_dia_y_mm,
            top_cover_mm, top_dia_x_mm, top_dia_y_mm,
            x_anchor_ubar_dia_mm, x_anchor_ubar_spacing_mm,
            y_anchor_ubar_dia_mm, y_anchor_ubar_spacing_mm, std=std,
            bottom_spacing_mm=bottom_spacing_mm)

    return result
