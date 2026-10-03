# -*- coding: utf-8 -*-
"""
T7.5 probe: render every RebarShape's BS 8666 sketch to OUT_DIR (read-only). With ASSIGN, also set
the images and add the BBS 'Shape Image' column inside a rolled-back TransactionGroup.
Scope: doc, EXT_ROOT, PYREVIT, OUT_DIR, ASSIGN (bool). Result: RESULT.
"""
import sys
import os
import traceback
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from Autodesk.Revit.UI import UIApplication

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)
_out = []
group = None
try:
    from nosa_utils.bootstrap import load_module
    from nosa_utils.revit_helpers import element_name
    lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Reinforcement.panel', 'RebarAutomate.pushbutton', 'lib')
    if lib not in sys.path:
        sys.path.insert(0, lib)
    images = load_module('shape_images', os.path.join(lib, 'shape_images.py'))
    shapes = images.all_shapes(doc)
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    paths = images.render_shapes(doc, shapes, OUT_DIR)
    _out.append(u'rendered {} of {} shapes'.format(len(paths), len(shapes)))
    for shape in shapes[:40]:
        polylines, labels = images.sketch_of(doc, shape)
        _out.append(u'  {}: {} curves, letters {}'.format(element_name(shape), len(polylines), labels))
    if ASSIGN:
        group = DB.TransactionGroup(doc, u'NOSA test - shape images')
        group.Start()
        t = DB.Transaction(doc, u'NOSA test - assign')
        t.Start()
        done = images.assign_images(doc, shapes, paths)
        bbs = [v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule) if element_name(v) == u'BBS']
        added = images.add_shape_image_column(doc, bbs[0]) if bbs else None
        t.Commit()
        _out.append(u'assigned {} images, BBS column added {}'.format(done, added))
        group.RollBack()
        group = None
except Exception:
    _out.append(traceback.format_exc())
finally:
    if group is not None and group.HasStarted():
        group.RollBack()
RESULT = u'\n'.join(_out)
