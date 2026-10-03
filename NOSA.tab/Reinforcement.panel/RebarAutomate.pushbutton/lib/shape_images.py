# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — BS 8666 shape images (T7.5): the sketch of every RebarShape (Revit's own
shape-browser geometry, its dimension letters beside each segment) drawn to a PNG, set as the
shape's image so the BBS schedule's 'Shape Image' column shows it, and reused by the Excel export.
Drawn in pure Python: System.Drawing from IronPython crashed Revit 2024 (2026-10-03).
"""
from __future__ import absolute_import, division, print_function, unicode_literals
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import shape_sketch

_FT = 304.8
IMAGE_PREFIX = u'NOSA_BS8666_'
SHAPE_IMAGE_FIELD = u'Shape Image'


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


def sketch_of(doc, shape):
    """(polylines in mm, one letter per polyline) from the shape's browser curves."""
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
    else:
        try:
            names = [_param_name(doc, pid) for pid in definition.GetParameters()]
            if polylines and names:
                labels[0] = u', '.join(n for n in names if n)
        except Exception:  # nosa-lint: disable=NOSA006 - an arc shape without parameters: no letters
            pass
    return polylines, labels


def render_png(path, polylines, labels):
    """Draw the sketch and its letters to a 300 dpi PNG (pure Python: png_sketch)."""
    import png_sketch
    pixel_lines, _to_px = shape_sketch.fit(polylines)
    canvas = png_sketch.draw_sketch(pixel_lines, shape_sketch.label_positions(pixel_lines, labels),
                                    shape_sketch.WIDTH, shape_sketch.HEIGHT)
    with open(path, 'wb') as f:
        f.write(canvas.png())
    return path


def render_shapes(doc, shapes, folder=None):
    """{shape id value: png path} for the given RebarShapes."""
    from nosa_utils.revit_helpers import element_name, get_id_value
    folder = folder or image_folder()
    out = {}
    for shape in shapes:
        try:
            polylines, labels = sketch_of(doc, shape)
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


def assign_images(doc, shapes, paths):
    """Set each shape's image (one ImageType per PNG, reloaded when it exists). Call in a transaction."""
    from Autodesk.Revit import DB  # Lazy import
    from nosa_utils.revit_helpers import element_name, get_id_value
    images = dict((element_name(i), i) for i in DB.FilteredElementCollector(doc).OfClass(DB.ImageType))
    done = 0
    for shape in shapes:
        path = paths.get(get_id_value(shape.Id))
        if not path:
            continue
        options = DB.ImageTypeOptions(path, False, DB.ImageTypeSource.Import)
        image = images.get(os.path.basename(path))
        if image is None:
            image = DB.ImageType.Create(doc, options)
            images[os.path.basename(path)] = image
        else:
            image.ReloadFrom(options)
        param = shape.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_IMAGE)
        if param is not None and not param.IsReadOnly:
            param.Set(image.Id)
            done += 1
    return done


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
