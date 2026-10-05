# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BS 8666 shape images (T7.5): the sketch of every RebarShape (Revit's own
shape-browser geometry, its dimension letters beside each segment) drawn to a PNG, stored on each
bar's NOSA_Rebar_Shape_Image (an Image parameter the BBS schedule shows) and reused by the Excel
export. Revit keeps a RebarShape's own 'Shape Image' read-only for the API (system shapes have no
family to edit), hence the bar parameter (2026-10-03).
Drawn in pure Python: System.Drawing from IronPython crashed Revit 2024 (2026-10-03).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import shape_sketch
from nosa_utils.telemetry import log_swallowed

_LOG = u'rebarautomate'

_FT = 304.8
IMAGE_PREFIX = u'NOSA_BS8666_'
SHAPE_IMAGE_FIELD = u'NOSA_Rebar_Shape_Image'


def image_folder():
    base = os.path.join(os.environ.get('APPDATA', _HERE), 'pyRevit', 'Extensions', 'NOSA.extension',
                        'NOSA_Configs', 'shape_sketches')
    if not os.path.isdir(base):
        os.makedirs(base)
    return base


def file_name(shape_name):
    return IMAGE_PREFIX + re.sub(r'[^A-Za-z0-9_-]+', u'_', shape_name or u'shape') + u'.png'


def _param_name(doc, param_id):
    from nosa_utils.revit_helpers import element_name
    element = doc.GetElement(param_id)
    return element_name(element) if element is not None else u''


def _plane_polylines(curves):
    """
    A bar's centreline (hooks included, no bend radii) in its own plane, mm: one polyline per
    straight, the longest one horizontal and the bar above it (a U opens upwards, as in BS 8666).
    """
    pts = _corner_points(curves)

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

    def unit(a):
        n = math.sqrt(dot(a, a))
        return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else None
    segs = [(a, b) for a, b in zip(pts[:-1], pts[1:]) if unit(sub(b, a)) is not None]
    if not segs:
        return []
    longest = max(segs, key=lambda s_: math.sqrt(dot(sub(s_[1], s_[0]), sub(s_[1], s_[0]))))
    u = unit(sub(longest[1], longest[0]))
    n = None
    for a, b in segs:
        n = unit(cross(u, sub(b, a)))
        if n is not None:
            break
    if n is None:
        n = unit(cross(u, (0.0, 0.0, 1.0))) or unit(cross(u, (0.0, 1.0, 0.0)))
    v = cross(n, u)
    flat = [(dot(p, u), dot(p, v)) for p in pts]
    base_v = dot(longest[0], v)
    if sum(q[1] for q in flat) / len(flat) < base_v:        # the bar above its longest straight
        flat = [(x, -y) for x, y in flat]
    return [[a, b] for a, b in zip(flat[:-1], flat[1:]) if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6]


def _corner_points(curves):
    """
    Vertices of a bar's straights, mm: hook bends stay arcs even without bend radii, so two
    straights an arc joins meet at the intersection of their lines.
    """
    from Autodesk.Revit import DB  # Lazy import
    lines = [c for c in curves if isinstance(c, DB.Line)]
    if not lines:
        return []

    def mm(p):
        return (p.X * _FT, p.Y * _FT, p.Z * _FT)
    pts = [mm(lines[0].GetEndPoint(0))]
    for a, b in zip(lines[:-1], lines[1:]):
        a1, b0 = a.GetEndPoint(1), b.GetEndPoint(0)
        if a1.DistanceTo(b0) < 1e-6:
            pts.append(mm(a1))
            continue
        # closest approach of the two (coplanar) lines: the corner the arc rounds off
        d1, d2 = a.Direction, b.Direction
        w = a1 - b0
        aa, bb, cc, dd, ee = d1.DotProduct(d1), d1.DotProduct(d2), d2.DotProduct(d2), d1.DotProduct(w), d2.DotProduct(w)
        den = aa * cc - bb * bb
        if abs(den) < 1e-12:
            pts.extend([mm(a1), mm(b0)])
            continue
        t = (bb * ee - cc * dd) / den
        pts.append(mm(a1 + d1.Multiply(t)))
    pts.append(mm(lines[-1].GetEndPoint(1)))
    return pts


def _segment_letters(doc, definition):
    from Autodesk.Revit.DB import Structure as DBS
    names = []
    for i in range(definition.NumberOfSegments):
        name = u''
        for constraint in definition.GetSegment(i).GetConstraints():
            if isinstance(constraint, DBS.RebarShapeConstraintSegmentLength):
                name = _param_name(doc, constraint.GetParamId())
                break
        names.append(name)
    return names


def sketch_from_bar(doc, shape, rebar):
    """
    (polylines mm, labels) from a real bar of this shape: hooks drawn at their true angle and side,
    lettered with the shape's dimensions no segment carries (shape 52: C, D; crosstie 99: B, C),
    each hook letter set at the hook's tip. None when the bar does not match the shape's segments.
    """
    from Autodesk.Revit.DB import Structure as DBS
    definition = shape.GetRebarShapeDefinition()
    if not isinstance(definition, DBS.RebarShapeDefinitionBySegments):
        return None
    curves = list(rebar.GetCenterlineCurves(False, False, True, DBS.MultiplanarOption.IncludeOnlyPlanarCurves, 0))
    if not curves:
        return None
    polylines = _plane_polylines(curves)
    names = _segment_letters(doc, definition)
    hooks = [bool(shape.GetDefaultHookAngle(end)) for end in (0, 1)]
    if len(polylines) != len(names) + sum(hooks):
        return None
    spare = [n for n in _shape_letters(doc, definition) if n not in names]
    labels = list(names)
    if hooks[0]:
        labels.insert(0, (spare.pop(0) if spare else u'', 'start'))
    if hooks[1]:
        labels.append((spare.pop(0) if spare else u'', 'end'))
    return polylines, labels


def sketch_of(doc, shape, rebar=None):
    """(polylines in mm, one letter per polyline): from a real bar of the shape when given, else
    from the shape's browser curves."""
    if rebar is not None:
        try:
            sketch = sketch_from_bar(doc, shape, rebar)
            if sketch is not None:
                return sketch
        except Exception:
            log_swallowed(_LOG, u'sketch_from_bar')
    from Autodesk.Revit import DB  # Lazy import
    from Autodesk.Revit.DB import Structure as DBS
    polylines, kinds = [], []
    for curve in shape.GetCurvesForBrowser():
        pts = [(p.X * _FT, p.Y * _FT) for p in curve.Tessellate()]
        polylines.append(pts)
        kinds.append('arc' if not isinstance(curve, DB.Line) else 'line')
    definition = shape.GetRebarShapeDefinition()
    labels = [u''] * len(polylines)
    if isinstance(definition, DBS.RebarShapeDefinitionBySegments):
        names = []
        for i in range(definition.NumberOfSegments):
            name = u''
            for constraint in definition.GetSegment(i).GetConstraints():
                if isinstance(constraint, DBS.RebarShapeConstraintSegmentLength):
                    name = _param_name(doc, constraint.GetParamId())
                    break
            names.append(name)
        if len(names) == len(polylines):
            labels = names
        else:                                 # extra bend arcs in the sketch: letters on the straights
            straight = [i for i, k in enumerate(kinds) if k == 'line']
            for i, name in zip(straight, names):
                labels[i] = name
    elif polylines:
        # arc shapes (BS 8666 67, 75, 77): the definition lists every shape parameter of the
        # family, so only the arc's own dimension letter is written
        labels[0] = u'A'
        return polylines, labels
    hooks = _hook_lines(shape, polylines, kinds)
    if hooks:
        # the hooks are not in Revit's browser sketch: drawn here and lettered with the shape's
        # dimensions no segment carries (shape 52: C and D; the crosstie 99: B and C)
        spare = [n for n in _shape_letters(doc, definition) if n not in labels]
        for k, line in enumerate(hooks):
            polylines.append(line)
            labels.append((spare[k] if k < len(spare) else u'', 'end'))
    return polylines, labels


def _shape_letters(doc, definition):
    """The single-letter dimensions (A..F) of a shape, in order; R, H and the like are left out."""
    names = []
    try:
        for pid in definition.GetParameters():
            name = _param_name(doc, pid)
            if len(name) == 1 and name in u'ABCDEF' and name not in names:
                names.append(name)
    except Exception:
        log_swallowed(_LOG, u'_shape_letters')
    return sorted(names)


def _hook_lines(shape, polylines, kinds):
    """
    [start hook, end hook] polylines (mm, sketch plane) for the hooks the shape defines: a leg of
    a quarter of the longest straight, turned by the hook angle towards the inside of the shape.
    """
    straights = [line for line, kind in zip(polylines, kinds) if kind == 'line' and len(line) >= 2]
    if not straights:
        return []
    longest = max(math.hypot(l[-1][0] - l[0][0], l[-1][1] - l[0][1]) for l in straights)
    leg = 0.25 * longest
    pts = [p for line in polylines for p in line]
    cx = sum(p[0] for p in pts) / float(len(pts))
    cy = sum(p[1] for p in pts) / float(len(pts))
    out = []
    for end in (0, 1):
        try:
            angle = shape.GetDefaultHookAngle(end)
        except Exception:
            angle = 0
        if not angle:
            continue
        line = straights[0] if end == 0 else straights[-1]
        tip, back = (line[0], line[1]) if end == 0 else (line[-1], line[-2])
        dx, dy = tip[0] - back[0], tip[1] - back[1]
        norm = math.hypot(dx, dy) or 1.0
        dx, dy = dx / norm, dy / norm                    # running out of the bar at this end
        turn = math.radians(angle)
        best = None
        for sign in (1.0, -1.0):                         # bend the side that points inwards
            c, s_ = math.cos(sign * turn), math.sin(sign * turn)
            hx, hy = dx * c - dy * s_, dx * s_ + dy * c
            end_pt = (tip[0] + hx * leg, tip[1] + hy * leg)
            score = math.hypot(end_pt[0] - cx, end_pt[1] - cy)
            if best is None or score < best[0]:
                best = (score, end_pt)
        out.append([tip, best[1]])
    return out


def render_png(path, polylines, labels):
    """Draw the sketch and its letters to a 300 dpi PNG (pure Python: png_sketch)."""
    import png_sketch
    pixel_lines, _to_px = shape_sketch.fit(polylines)
    canvas = png_sketch.draw_sketch(pixel_lines, shape_sketch.label_positions(pixel_lines, labels),
                                    shape_sketch.WIDTH, shape_sketch.HEIGHT)
    with open(path, 'wb') as f:
        f.write(canvas.png(dpi=shape_sketch.DPI))
    return path


def examples(doc, shapes):
    """{shape id value: one Rebar of that shape in the model} (the sketch's real geometry)."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import get_id_value
    want = set(get_id_value(s.Id) for s in shapes)
    out = {}
    for rebar in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rebar)             .WhereElementIsNotElementType():
        shape_id = _shape_id(rebar)
        if shape_id is None:
            continue
        value = get_id_value(shape_id)
        if value in want and value not in out:
            out[value] = rebar
            if len(out) == len(want):
                break
    return out


def render_shapes(doc, shapes, folder=None):
    """{shape id value: png path} for the given RebarShapes."""
    from nosa_utils.revit_helpers import element_name, get_id_value
    folder = folder or image_folder()
    bars = examples(doc, shapes)
    out = {}
    for shape in shapes:
        try:
            polylines, labels = sketch_of(doc, shape, bars.get(get_id_value(shape.Id)))
            if not polylines:
                continue
            out[get_id_value(shape.Id)] = render_png(
                os.path.join(folder, file_name(element_name(shape))), polylines, labels)
        except Exception:
            continue
    return out


def all_shapes(doc):
    from Autodesk.Revit import DB  # Lazy import
    from Autodesk.Revit.DB import Structure as DBS
    return list(DB.FilteredElementCollector(doc).OfClass(DBS.RebarShape))


def _image_file(image):
    try:
        return os.path.basename(image.Path or u'')
    except Exception:
        return u''


def image_types(doc, shapes, paths):
    """
    {shape id value: ImageType id}, one ImageType per PNG (reloaded when it exists). In a transaction.
    The ImageType is named by the bare shape code ("21"): a BBS schedule view lists the image by
    name, so it reads like the shape code column; the sheet shows the sketch itself.
    """
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name, get_id_value
    images = {}
    for i in DB.FilteredElementCollector(doc).OfClass(DB.ImageType):
        images[_image_file(i) or element_name(i)] = i
    out = {}
    for shape in shapes:
        path = paths.get(get_id_value(shape.Id))
        if not path:
            continue
        options = DB.ImageTypeOptions(path, False, DB.ImageTypeSource.Import)
        try:
            # Revit ignores the PNG's own pHYs (reads 72 dpi): the sketch keeps its 30 x 15 mm
            options.Resolution = shape_sketch.DPI
        except Exception:
            log_swallowed(_LOG, u'image_types resolution')
        image = images.get(os.path.basename(path))
        if image is None:
            image = DB.ImageType.Create(doc, options)
            images[os.path.basename(path)] = image
        else:
            image.ReloadFrom(options)
        code = (element_name(shape) or u'').strip()
        if code and element_name(image) != code:
            try:
                image.Name = code
            except Exception:  # nosa-lint: disable=NOSA006 - name taken: the file name stays
                pass
        out[get_id_value(shape.Id)] = image.Id
    return out


def _shape_id(rebar):
    """The bar's RebarShape id, or None for a FreeForm bundle of several shapes (no single sketch)."""
    try:
        return rebar.GetShapeId()
    except Exception:  # nosa-lint: disable=NOSA006 - "matched with multiple shapes": no sketch
        return None


def stamp_bars(doc, rebars, image_ids):
    """Point every bar's NOSA_Rebar_Shape_Image at the sketch of its shape. In a transaction."""
    from nosa_utils.revit_helpers import get_id_value
    done = 0
    for rebar in rebars:
        shape_id = _shape_id(rebar)
        image_id = image_ids.get(get_id_value(shape_id)) if shape_id is not None else None
        param = rebar.LookupParameter(SHAPE_IMAGE_FIELD)
        if image_id is None or param is None or param.IsReadOnly:
            continue
        if param.Set(image_id):
            done += 1
    return done


def nosa_rebars(doc):
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils import shared_params
    return [r for r in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rebar)
            .WhereElementIsNotElementType() if shared_params.read(r, u'NOSA_Rebar_Batch_Id')]


def shapes_of(doc, rebars):
    seen, out = set(), []
    for rebar in rebars:
        shape_id = _shape_id(rebar)
        shape = doc.GetElement(shape_id) if shape_id is not None else None
        if shape is not None and shape.Id not in seen:
            seen.add(shape.Id)
            out.append(shape)
    return out


def add_shape_image_column(doc, schedule, after=u'Shape'):
    """Add the 'Shape Image' field to a rebar schedule, after its shape code; False if already there."""
    definition = schedule.Definition
    for i in range(definition.GetFieldCount()):
        if definition.GetField(i).GetName() == SHAPE_IMAGE_FIELD:
            return False
    field_def = None
    for schedulable in definition.GetSchedulableFields():
        if schedulable.GetName(doc) == SHAPE_IMAGE_FIELD:
            field_def = schedulable
            break
    if field_def is None:
        return False
    index = definition.GetFieldCount()
    for i in range(definition.GetFieldCount()):
        if definition.GetField(i).GetName() == after:
            index = i + 1
            break
    field = definition.InsertField(field_def, index)
    field.ColumnHeading = u'Shape'
    return True
