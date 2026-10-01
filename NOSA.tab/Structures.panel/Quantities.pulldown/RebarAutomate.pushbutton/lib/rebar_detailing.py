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


def _bar_reference(rebar):
    """Reference to the middle bar of a Rebar Set (its subelement), for tagging."""
    subelements = list(rebar.GetSubelements())
    if not subelements:
        return DB.Reference(rebar)
    return subelements[len(subelements) // 2].GetReference()


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
    try:
        tag = DB.IndependentTag.Create(
            doc, view.Id, DB.Reference(rebar), add_leader, DB.TagMode.TM_ADDBY_CATEGORY,
            orientation, point)
    except Exception:
        # Revit 2024 rejects a whole Rebar Set ("The reference can not be tagged"):
        # tag one of its bars instead (verified live 2026-10-01).
        tag = DB.IndependentTag.Create(
            doc, view.Id, _bar_reference(rebar), add_leader, DB.TagMode.TM_ADDBY_CATEGORY,
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


# ══════════════════════════════════════════════════════════════════════════
# F6 Enhancements — Multi-Rebar Annotation (MRA), smart offsets, auto-dims
# ══════════════════════════════════════════════════════════════════════════

def _read_tag_offset_from_params(rebar):
    """
    Read tag offsets from NOSA_Rebar_Tag_Offset_X/Y parameters if present.
    
    Args:
        rebar (DBS.Rebar): the rebar element to read from.
    
    Returns:
        (float, float, float): (dx_mm, dy_mm, dz_mm) offset tuple.
                              Returns (0.0, 0.0, 0.0) if parameters not found
                              or have no value.
    """
    try:
        # Try to get parameters by GUID (preferred) or by name (fallback)
        offset_x = 0.0
        offset_y = 0.0
        
        # Offset X
        try:
            import System
            guid_x = System.Guid('1fa47447-1b45-4516-8a07-a6590a69b83b')
            param_x = rebar.get_Parameter(guid_x)
            if param_x and param_x.HasValue:
                offset_x = param_x.AsDouble() * _MM_PER_FT  # Convert feet to mm
        except Exception:
            param_x = rebar.LookupParameter('NOSA_Rebar_Tag_Offset_X')
            if param_x and param_x.HasValue:
                offset_x = param_x.AsDouble() * _MM_PER_FT
        
        # Offset Y
        try:
            guid_y = System.Guid('245b5c8c-1813-4935-8c27-8d89df2d48f3')
            param_y = rebar.get_Parameter(guid_y)
            if param_y and param_y.HasValue:
                offset_y = param_y.AsDouble() * _MM_PER_FT
        except Exception:
            param_y = rebar.LookupParameter('NOSA_Rebar_Tag_Offset_Y')
            if param_y and param_y.HasValue:
                offset_y = param_y.AsDouble() * _MM_PER_FT
        
        return (offset_x, offset_y, 0.0)
    
    except Exception:
        return (0.0, 0.0, 0.0)


def create_rebar_tags_smart(doc, view, rebars, use_param_offsets=True,
                             fallback_offset_mm=(0.0, 0.0, 0.0),
                             orientation=None, tag_type_id=None, add_leader=False):
    """
    Enhanced version of create_rebar_tags that reads offsets from
    NOSA_Rebar_Tag_Offset_X/Y parameters per-bar, allowing fine-grained
    control of tag placement to avoid overlaps.
    
    Args:
        doc                 (DB.Document)
        view                (DB.View): the view to tag in.
        rebars              (list[DBS.Rebar]): the bars to tag.
        use_param_offsets   (bool): if True, reads NOSA_Rebar_Tag_Offset_X/Y
                            from each bar; if False or params not found, uses
                            fallback_offset_mm.
        fallback_offset_mm  (float, float, float): default offset when
                            use_param_offsets is False or params not found.
        orientation         (DB.TagOrientation or None)
        tag_type_id         (DB.ElementId or None)
        add_leader          (bool)
    
    Returns:
        (list[DB.IndependentTag], list[unicode]) — created tags and errors.
    """
    tags = []
    errors = []
    
    for rebar in rebars:
        try:
            if use_param_offsets:
                offset_mm = _read_tag_offset_from_params(rebar)
                # If no offset found in params, use fallback
                if offset_mm == (0.0, 0.0, 0.0):
                    offset_mm = fallback_offset_mm
            else:
                offset_mm = fallback_offset_mm
            
            tag = create_rebar_tag(doc, view, rebar, offset_mm, orientation,
                                  tag_type_id, add_leader)
            tags.append(tag)
        except Exception as e:
            errors.append(u'Rebar {}: {}'.format(rebar.Id, e))
    
    return tags, errors


def list_mra_types(doc):
    """
    All MultiReferenceAnnotationType elements in the document
    (shown in Project Browser as Multi-Rebar Annotations).

    Returns:
        list[DB.MultiReferenceAnnotationType]
    """
    return list(DB.FilteredElementCollector(doc)
                .OfClass(DB.MultiReferenceAnnotationType)
                .ToElements())


def list_rebar_tag_types(doc):
    """
    All IndependentTag types in OST_RebarTags (Project Browser:
    Annotation Symbols → Rebar Tags / NOSA Rebar Tag).

    Returns:
        list[DB.ElementType]
    """
    return list(DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_RebarTags)
                .WhereElementIsElementType()
                .ToElements())


FULL_LABEL = u'Full label'
MARK_ONLY = u'Mark only'
_CUT_VIEW_TYPES = (u'Section', u'Detail')


def label_kind_for_view_type(view_type_name):
    """'Mark only' in sections and details, else 'Full label' (plans and elevations: user rule)."""
    return MARK_ONLY if view_type_name in _CUT_VIEW_TYPES else FULL_LABEL


def swap_label_kind(type_name, kind):
    """'Full label - Arrow' -> 'Mark only - Arrow' (keeps the leader end); None if not a NOSA name."""
    for prefix in (FULL_LABEL, MARK_ONLY):
        if type_name.startswith(prefix + u' - '):
            return kind + type_name[len(prefix):]
    return None


def tag_type_for_view(doc, view, chosen_type_id=None):
    """
    NOSA Rebar Tag type for this view: the chosen leader end (Dot by default) with
    Mark only in sections and Full label elsewhere. Falls back to the chosen type.
    """
    types = dict((DB.Element.Name.GetValue(t), t.Id) for t in list_rebar_tag_types(doc))
    kind = label_kind_for_view_type(str(view.ViewType))
    base = FULL_LABEL + u' - Dot'
    if chosen_type_id is not None:
        chosen = doc.GetElement(chosen_type_id)
        base = DB.Element.Name.GetValue(chosen) if chosen is not None else base
    wanted = swap_label_kind(base, kind)
    if wanted and wanted in types:
        return types[wanted]
    return chosen_type_id


def create_multi_rebar_annotation(doc, view, rebars, mra_type=None,
                                   dim_offset_mm=300.0, tag_has_leader=False):
    """
    Create a Multi-Rebar Annotation (MRA) for the given rebars.

    Uses the documented Revit API:
      MultiReferenceAnnotation.Create(doc, viewId, MultiReferenceAnnotationOptions)

    Args:
        doc              (DB.Document)
        view             (DB.View): owner view for the annotation.
        rebars           (list[DBS.Rebar]): bars to dimension/tag together
                         (typically parallel members of one set).
        mra_type         (DB.MultiReferenceAnnotationType or None): if None,
                         uses the first available type in the document.
        dim_offset_mm    (float): offset of the dimension line from the bar
                         run, measured along view.UpDirection, mm.
        tag_has_leader   (bool): TagHasLeader on the options object.

    Returns:
        DB.MultiReferenceAnnotation on success, or None on failure.

    Note:
        API CONFIDENCE: MEDIUM — geometry heuristics (sort along
        view.RightDirection, offset along UpDirection) are reasonable
        for plan views; verify on section/elevation views.
    """
    if not rebars:
        return None

    try:
        from System.Collections.Generic import List as NetList

        if mra_type is None:
            types = list_mra_types(doc)
            if not types:
                return None
            mra_type = types[0]

        centers = []
        for rebar in rebars:
            bbox = rebar.get_BoundingBox(view)
            if bbox is not None:
                centers.append((bbox.Min + bbox.Max).Multiply(0.5))
        if not centers:
            return None

        right = view.RightDirection
        up = view.UpDirection

        def _along_right(pt):
            return pt.DotProduct(right)

        sorted_centers = sorted(centers, key=_along_right)
        p0 = sorted_centers[0]
        p1 = sorted_centers[-1]
        run = p1 - p0
        if run.GetLength() < 1.0 / _MM_PER_FT:
            direction = right
        else:
            direction = run.Normalize()

        offset = up.Multiply(dim_offset_mm / _MM_PER_FT)
        mid = (p0 + p1).Multiply(0.5)

        options = DB.MultiReferenceAnnotationOptions(mra_type)
        options.DimensionPlaneNormal = view.ViewDirection
        options.DimensionLineDirection = direction
        options.DimensionLineOrigin = p0 + offset
        options.TagHeadPosition = mid + offset.Multiply(1.5)
        try:
            options.TagHasLeader = bool(tag_has_leader)
        except Exception:
            pass

        ids = NetList[DB.ElementId]()
        for rebar in rebars:
            ids.Add(rebar.Id)
        options.SetElementsToDimension(ids)

        return DB.MultiReferenceAnnotation.Create(doc, view.Id, options)
    except Exception:
        return None


def create_orthogonal_detail_sections(doc, host, depth_margin_mm=200.0):
    """
    Create two orthogonal detail sections (X and Y) through `host`.

    Returns:
        (list[DB.ViewSection], list[unicode]) — created sections and
        per-axis error messages (never raises).
    """
    sections = []
    errors = []
    vft = get_detail_section_view_family_type(doc)
    if vft is None:
        errors.append(u'No Detail Section view type found in this project.')
        return sections, errors

    for axis in ('X', 'Y'):
        section = create_rebar_detail_section(
            doc, host, vft.Id, cut_axis=axis, depth_margin_mm=depth_margin_mm)
        if section is None:
            errors.append(u'Could not create {}-axis detail section.'.format(axis))
        else:
            sections.append(section)
    return sections, errors


def create_stirrup_dimension_smart(doc, view, stirrup_rebars, host=None,
                                    offset_mm=300.0):
    """
    Enhanced version of create_stirrup_dimension that calculates dim_line
    automatically from the host element's axis, instead of requiring the
    caller to supply it.
    
    Args:
        doc             (DB.Document)
        view            (DB.View): the view to place the dimension in.
        stirrup_rebars  (list[DBS.Rebar]): the stirrups to dimension, in
                        run order — at least 2.
        host            (DB.Element or None): the host element (beam/column)
                        to extract the axis from. If None, falls back to
                        computing axis from first and last stirrup centroids.
        offset_mm       (float): perpendicular offset from the axis for the
                        dimension line, mm.
    
    Returns:
        DB.Dimension on success, or None on failure.
    
    Note:
        This function tries to automatically determine the axis. If host is
        provided and has a Location.Curve (e.g., FamilyInstance beam/column),
        uses that. Otherwise, computes axis from stirrup positions.
    """
    if len(stirrup_rebars) < 2:
        return None
    
    try:
        # Try to get axis from host
        axis_line = None
        
        if host is not None:
            try:
                loc = host.Location
                if hasattr(loc, 'Curve') and loc.Curve is not None:
                    axis_line = loc.Curve
            except Exception:
                pass
        
        # Fallback: compute axis from first and last stirrup
        if axis_line is None:
            first_bbox = stirrup_rebars[0].get_BoundingBox(view)
            last_bbox = stirrup_rebars[-1].get_BoundingBox(view)
            
            if first_bbox is None or last_bbox is None:
                return None
            
            p1 = (first_bbox.Min + first_bbox.Max).Multiply(0.5)
            p2 = (last_bbox.Min + last_bbox.Max).Multiply(0.5)
            axis_line = DB.Line.CreateBound(p1, p2)
        
        # Get axis direction and perpendicular offset
        axis_dir = (axis_line.GetEndPoint(1) - axis_line.GetEndPoint(0)).Normalize()
        
        # Perpendicular direction (in view plane, assuming Z-up)
        perp_dir = DB.XYZ(-axis_dir.Y, axis_dir.X, 0.0).Normalize()
        offset_vec = perp_dir.Multiply(offset_mm / _MM_PER_FT)
        
        # Create dimension line parallel to axis, offset to one side
        p1_offset = axis_line.GetEndPoint(0) + offset_vec
        p2_offset = axis_line.GetEndPoint(1) + offset_vec
        dim_line = DB.Line.CreateBound(p1_offset, p2_offset)
        
        # Create dimension
        refs = DB.ReferenceArray()
        for bar in stirrup_rebars:
            refs.Append(DB.Reference(bar))
        
        return doc.Create.NewDimension(view, dim_line, refs)
    
    except Exception:
        return None


def tag_rebar_set_along_run(doc, view, rebar_set, tag_type_id=None, 
                             dim_offset_mm=300.0):
    """
    Tag and dimension a single Rebar element that uses ShapeDrivenAccessor
    (i.e., a "set" of bars along a run, like stirrups or mat distribution).
    
    Creates ONE tag at the first bar position, plus a dimension showing
    the spacing along the run.
    
    Args:
        doc             (DB.Document)
        view            (DB.View): the view to tag and dimension in.
        rebar_set       (DBS.Rebar): a single Rebar element (not a list),
                        typically created with ShapeDrivenAccessor and
                        representing multiple bars along a run.
        tag_type_id     (DB.ElementId or None): specific tag type.
        dim_offset_mm   (float): perpendicular offset for dimension line, mm.
    
    Returns:
        (DB.IndependentTag or None, DB.Dimension or None) — the tag and
        dimension created, or None for each if creation failed.
    
    Note:
        This is a convenience function for the common pattern of "one tag +
        one dimension" for a distributed rebar set. For more complex
        arrangements, call create_rebar_tag and create_stirrup_dimension_smart
        separately.
    """
    tag = None
    dim = None
    
    try:
        # Create tag at rebar's first position (using bounding box center)
        try:
            tag = create_rebar_tag(doc, view, rebar_set, offset_mm=(0.0, 0.0, 0.0),
                                  orientation=DB.TagOrientation.Horizontal,
                                  tag_type_id=tag_type_id, add_leader=False)
        except Exception:
            pass
        
        # For dimension, we need to extract individual bar positions
        # For a ShapeDrivenAccessor rebar, we can't easily get individual
        # bar positions without GetCenterlineCurves, which varies by version.
        # For now, skip dimension creation for single Rebar sets.
        # (This would require version-specific code or a more complex approach)
        
        # TODO: Implement dimension extraction for ShapeDrivenAccessor
        # This requires iterating through bar positions, which is
        # version-dependent. For now, return tag only.
        
    except Exception:
        pass
    
    return tag, dim
