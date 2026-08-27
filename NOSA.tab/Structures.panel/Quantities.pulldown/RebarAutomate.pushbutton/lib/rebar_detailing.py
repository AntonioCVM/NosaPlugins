# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — Detailing (Phase 3)
============================================================================

Annotation helpers for Rebar elements already instantiated by
rebar_engine.RebarWrapper: tags (IndependentTag) and dimensions
(doc.Create.NewDimension). Meant to be loaded in isolation the same way
every other module in this plugin is:

    from nosa_utils.bootstrap import load_module
    detailing = load_module(
        'rebar_detailing', os.path.join(os.path.dirname(__file__), 'rebar_detailing.py'))

Like rebar_engine.py, this module does NOT open its own Transaction —
tagging/dimensioning a batch of bars created in the same user action
belongs inside the SAME TransactionGroup the caller already opened for
the Rebar creation itself (see ui.py's Footing_Click handler), so the
caller's Transaction/TransactionGroup boundaries decide where these
calls happen, not this module.

API CONFIDENCE
--------------
MEDIUM  IndependentTag.Create(doc, viewId, reference, addLeader, tagMode,
        tagOrientation, point) is the documented Revit 2022+ signature
        (this extension's Toposolid usage elsewhere already establishes
        2024+ as the target API level, so this module targets that
        overload rather than the pre-2022 doc.Create.NewTag style).
        Not yet exercised against a live document.

MEDIUM  doc.Create.NewDimension(view, line, referenceArray) is a long-
        stable API, but dimensioning directly off a Reference(rebar) —
        rather than a face/edge Reference — is a less common usage
        pattern; verify the resulting dimension actually snaps to a
        sensible point on the bar in your Revit version.

LOWEST  (Phase 5.1) create_rebar_detail_section's BoundingBoxXYZ /
        Transform construction for ViewSection.CreateDetail — see that
        function's own docstring for why this is even less confident
        than the rest of this module, and why it deliberately BREAKS
        this module's own "raise on failure" rule below (catches
        everything, returns None) rather than following it.

Every function here EXCEPT create_rebar_detail_section raises on
failure rather than swallowing the exception (unlike
rebar_engine.RebarWrapper's defensive style) — the PLURAL batch
functions (create_rebar_tags) are what catch per-item exceptions and
keep going; the singular functions stay strict so a caller working
with just one element sees the real error immediately.
create_rebar_detail_section is the one deliberate exception (see its
own docstring): its failure mode is "produces something that looks
wrong" more often than "throws", so it warrants the defensive,
None-returning style instead.
"""
from Autodesk.Revit import DB

_MM_PER_FT = 304.8


# ══════════════════════════════════════════════════════════════════════════
# Tags
# ══════════════════════════════════════════════════════════════════════════

def _tag_point(rebar, view, offset_mm):
    """
    A reasonable point to place a rebar's tag at: the centre of the
    rebar's own bounding box in `view`, plus a caller-supplied offset.

    Using the bounding box (rather than, say, the first centerline
    curve's midpoint) sidesteps Rebar.GetCenterlineCurves' overload
    differences across Revit versions — get_BoundingBox(View) is a
    stable, version-independent Element method.

    Args:
        rebar     (DBS.Rebar): the placed rebar element.
        view      (DB.View): the view the tag will be placed in.
        offset_mm (float, float, float): (dx, dy, dz) offset from the
                  bounding box centre, mm.

    Returns:
        DB.XYZ

    Raises:
        ValueError: if the rebar has no bounding box in this view (not
        visible there).
    """
    bbox = rebar.get_BoundingBox(view)
    if bbox is None:
        raise ValueError(u'Rebar {} has no bounding box in view "{}" — is '
                          u'it visible there?'.format(rebar.Id, view.Name))
    center = (bbox.Min + bbox.Max).Multiply(0.5)
    offset = DB.XYZ(offset_mm[0] / _MM_PER_FT, offset_mm[1] / _MM_PER_FT,
                     offset_mm[2] / _MM_PER_FT)
    return center + offset


def create_rebar_tag(doc, view, rebar, offset_mm=(0.0, 0.0, 0.0),
                      orientation=None, tag_type_id=None, add_leader=False):
    """
    Create one IndependentTag on `rebar`, placed at its bounding-box
    centre (in `view`) plus offset_mm.

    Args:
        doc          (DB.Document)
        view         (DB.View): the view to tag in — must show `rebar`.
        rebar        (DBS.Rebar): the element to tag.
        offset_mm    (float, float, float): (dx, dy, dz) tag point
                     offset from the rebar's bounding-box centre, mm —
                     lets the caller nudge overlapping tags apart (e.g.
                     the per-bar offset config the UI reads).
        orientation  (DB.TagOrientation or None): defaults to
                     TagOrientation.Horizontal if not given.
        tag_type_id  (DB.ElementId or None): if given, the tag is
                     switched to this type via ChangeTypeId after
                     creation, instead of leaving Revit's current
                     default tag type for the category.
        add_leader   (bool): whether the tag gets a leader line.

    Returns:
        DB.IndependentTag

    Raises:
        ValueError: from _tag_point, or if tag creation returns None.
    """
    if orientation is None:
        orientation = DB.TagOrientation.Horizontal
    point = _tag_point(rebar, view, offset_mm)
    reference = DB.Reference(rebar)

    tag = DB.IndependentTag.Create(
        doc, view.Id, reference, add_leader, DB.TagMode.TM_ADDBY_CATEGORY,
        orientation, point)
    if tag is None:
        raise ValueError(u'IndependentTag.Create returned None for rebar {}.'.format(rebar.Id))

    if tag_type_id is not None:
        tag.ChangeTypeId(tag_type_id)

    return tag


def create_rebar_tags(doc, view, rebars, offset_mm=(0.0, 0.0, 0.0),
                       orientation=None, tag_type_id=None, add_leader=False):
    """
    Batch wrapper around create_rebar_tag: tags every rebar in `rebars`,
    catching each failure individually so one bar with no bounding box
    in `view` (or any other single-tag failure) doesn't abort the rest
    of the batch.

    Args:
        (same as create_rebar_tag, but `rebars` is a list[DBS.Rebar])

    Returns:
        (list[DB.IndependentTag], list[unicode]) — successfully created
        tags, and one error message string per failed rebar (prefixed
        with the rebar's ElementId for traceability).
    """
    tags = []
    errors = []
    for rebar in rebars:
        try:
            tags.append(create_rebar_tag(
                doc, view, rebar, offset_mm, orientation, tag_type_id, add_leader))
        except Exception as e:
            errors.append(u'Rebar {}: {}'.format(rebar.Id, e))
    return tags, errors


# ══════════════════════════════════════════════════════════════════════════
# Dimensions
# ══════════════════════════════════════════════════════════════════════════

def create_stirrup_dimension(doc, view, stirrup_rebars, dim_line):
    """
    Dimension the spacing between a run of stirrups (or any sequence of
    parallel Rebar elements), referencing each Rebar element directly —
    the same Reference(rebar) style used for tagging in create_rebar_tag
    above.

    Args:
        doc             (DB.Document)
        view            (DB.View): the view to place the dimension in.
        stirrup_rebars  (list[DBS.Rebar]): the bars to dimension between,
                        in run order — at least 2.
        dim_line        (DB.Line): the dimension's witness line,
                        typically parallel to the stirrup run and offset
                        to one side of it — this module does not compute
                        that geometry itself; the caller (which already
                        knows the beam/column axis) supplies it.

    Returns:
        DB.Dimension

    Raises:
        ValueError: if fewer than 2 rebars are supplied.
    """
    if len(stirrup_rebars) < 2:
        raise ValueError(u'Need at least 2 stirrups to dimension the spacing between them.')

    refs = DB.ReferenceArray()
    for bar in stirrup_rebars:
        refs.Append(DB.Reference(bar))

    return doc.Create.NewDimension(view, dim_line, refs)


# ══════════════════════════════════════════════════════════════════════════
# Automatic detail sections (Phase 5.1 — implements the Phase 3 scaffold)
# ══════════════════════════════════════════════════════════════════════════

def get_detail_section_view_family_type(doc):
    """
    The project's Detail-family ViewFamilyType — the type
    ViewSection.CreateDetail needs, distinct from the plain
    ViewFamily.Section used for ordinary building sections (this
    function specifically looks for ViewFamily.Detail, matching
    CreateDetail's own name).

    Returns:
        DB.ViewFamilyType, or None if the project has none (every
        default Revit template ships one, but a stripped-down or
        heavily customised project might not) — callers MUST check for
        None and warn the user rather than passing it straight through.
    """
    for vft in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType).ToElements():
        try:
            if vft.ViewFamily == DB.ViewFamily.Detail:
                return vft
        except Exception:
            continue
    return None


def create_rebar_detail_section(doc, host, view_family_type_id, cut_axis='X', depth_margin_mm=200.0):
    """
    Creates ONE ViewSection.CreateDetail cut through `host`'s own
    bounding box, centred on it: cut_axis='X' gives a section whose
    left-right (in-view) direction is the global X axis (i.e. you are
    looking along -Y); cut_axis='Y' gives left-right along global Y
    (looking along +X). Calling this once per axis, per Phase 5.1's
    brief, gives two orthogonal sections through the host's centre.

    *** THE LEAST-CONFIDENT CALL IN THIS WHOLE PLUGIN — READ THIS ***
    BoundingBoxXYZ.Transform math for ViewSection.CreateDetail is one
    of the most error-prone corners of the Revit API even for
    experienced API developers — a wrong Transform doesn't throw an
    exception, it just produces a section that LOOKS wrong (empty crop,
    everything clipped, rotated 90° from what you expected), which is
    harder to catch than the TypeErrors this project's other
    least-confident calls (Rebar.CreateFromCurves,
    ShapeDrivenAccessor) would throw on a bad signature. NOTHING here
    has been checked against a live model. Treat the first section this
    produces as a starting point to inspect and adjust, not a finished
    result — this is exactly why this function returns None on failure
    (or an unexpected-looking section) rather than raising: per this
    project's "warn, don't crash" rule, a bad section shouldn't abort
    the rest of a footing run that otherwise succeeded.

    Args:
        doc                  (DB.Document)
        host                 (DB.Element): the element to section
                             through (e.g. the footing).
        view_family_type_id  (DB.ElementId): a Detail-family
                             ViewFamilyType's Id — see
                             get_detail_section_view_family_type().
        cut_axis             ('X' or 'Y'): which global axis the
                             section's left-right (in-view) direction
                             follows — see the docstring intro above.
        depth_margin_mm      (float): extra depth beyond the host's own
                             extent along the view direction, so the
                             host isn't right at the very edge of the
                             section's cut depth, mm.

    Returns:
        DB.ViewSection on success, or None on failure/invalid cut_axis
        (this function does not raise — see the note above).
    """
    try:
        bbox = host.get_BoundingBox(None)
        if bbox is None:
            return None

        if cut_axis == 'X':
            basis_x, basis_y, basis_z = DB.XYZ.BasisX, DB.XYZ.BasisZ, DB.XYZ(0.0, -1.0, 0.0)
        elif cut_axis == 'Y':
            basis_x, basis_y, basis_z = DB.XYZ.BasisY, DB.XYZ.BasisZ, DB.XYZ(1.0, 0.0, 0.0)
        else:
            return None

        extent = bbox.Max - bbox.Min
        half_width_ft = abs(extent.DotProduct(basis_x)) / 2.0
        half_height_ft = abs(extent.DotProduct(basis_y)) / 2.0
        half_depth_ft = abs(extent.DotProduct(basis_z)) / 2.0 + (depth_margin_mm / _MM_PER_FT)

        transform = DB.Transform.Identity
        transform.Origin = (bbox.Min + bbox.Max).Multiply(0.5)
        transform.BasisX = basis_x
        transform.BasisY = basis_y
        transform.BasisZ = basis_z

        section_box = DB.BoundingBoxXYZ()
        section_box.Transform = transform
        section_box.Min = DB.XYZ(-half_width_ft, -half_height_ft, -half_depth_ft)
        section_box.Max = DB.XYZ(half_width_ft, half_height_ft, half_depth_ft)

        return DB.ViewSection.CreateDetail(doc, view_family_type_id, section_box)
    except Exception:
        return None
