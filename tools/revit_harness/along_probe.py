# -*- coding: utf-8 -*-
"""Debug (2026-10-26): what _along_concrete sees in each slab section - the member box and each framing box."""
import io

import rebar_presentation as rp
from nosa_utils import presentation
from Autodesk.Revit import DB

_path = OUT + '.along'
io.open(_path, 'w', encoding='utf-8').close()
_orig = rp._along_concrete


def _along(doc, view, hosts, box):
    out = _orig(doc, view, hosts, box)
    lines = [u'{} | member {} | found {}'.format(view.Name, [round(x) for x in box], len(out))]
    crop = rp._clip_to_crop(view, (-1e9, -1e9, 1e9, 1e9))
    lines.append(u'   crop {}'.format([round(x) for x in crop]))
    for e in DB.FilteredElementCollector(doc, view.Id).OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
            .WhereElementIsNotElementType():
        bb = e.get_BoundingBox(None)
        pts = [rp._xy(view, DB.XYZ(x, y, z)) for x in (bb.Min.X, bb.Max.X) for y in (bb.Min.Y, bb.Max.Y)
               for z in (bb.Min.Z, bb.Max.Z)]
        b = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        lines.append(u'   beam {} box {} runs_under {}'.format(e.Id, [round(x) for x in b],
                                                              presentation.runs_under(b, box, 37.5)))
    with io.open(_path, 'a', encoding='utf-8') as fh:
        fh.write(u'\n'.join(lines) + u'\n')
    return out


rp._along_concrete = _along
_log.append(u'== along probe -> ' + _path)
