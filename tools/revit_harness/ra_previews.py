# -*- coding: utf-8 -*-
"""
Render every RebarAutomate preview canvas to PNG, inside Revit, without
showing the window. Same launcher as ra_harness.py (see run_ra.cs).

Scope variables: doc, CONTROLS (JSON), EXT_ROOT, PYREVIT, OUT_DIR.
Result: RESULT (unicode) — one line per canvas written.
"""
import sys
import os
import json
import __builtin__

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
from Autodesk.Revit.UI import UIApplication
from System.IO import FileStream, FileMode
from System.Windows import Size, Rect
from System.Windows.Media import PixelFormats, Brushes
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame

for _p in (os.path.join(PYREVIT, 'pyrevitlib'), os.path.join(PYREVIT, 'site-packages'),
           os.path.join(EXT_ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
__builtin__.__revit__ = UIApplication(doc.Application)

_log = []
try:
    from nosa_utils.bootstrap import load_module
    ra_lib = os.path.join(EXT_ROOT, 'NOSA.tab', 'Structures.panel', 'Quantities.pulldown',
                          'RebarAutomate.pushbutton', 'lib')
    ui = load_module('rebarautomate_ui', os.path.join(ra_lib, 'ui.py'))
    ui.forms.alert = lambda msg, *a, **k: _log.append(u'ALERT: ' + unicode(msg)) or True

    win = ui.RebarAutomateWindow(doc)
    win._is_loaded = True
    for name, value in json.loads(CONTROLS or '{}').items():
        control = getattr(win, name)
        if isinstance(value, bool):
            control.IsChecked = value
        else:
            control.Text = unicode(value)

    for update in ('_update_preview', '_update_column_preview', '_update_column_elevation_preview',
                   '_update_beam_preview', '_update_beam_elevation_preview', '_update_wall_preview'):
        try:
            getattr(win, update)()
        except Exception as e:
            _log.append(u'{} failed: {}'.format(update, e))

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    for name in ('PreviewCanvas', 'ColumnPreviewCanvas', 'ColumnElevationCanvas', 'BeamPreviewCanvas',
                 'BeamElevationCanvas', 'WallSectionCanvas', 'WallPreviewCanvas'):
        canvas = getattr(win, name)
        w, h = int(canvas.Width), int(canvas.Height)
        canvas.Background = Brushes.White
        canvas.Measure(Size(w, h))
        canvas.Arrange(Rect(0, 0, w, h))
        canvas.UpdateLayout()
        bmp = RenderTargetBitmap(w * 2, h * 2, 192, 192, PixelFormats.Pbgra32)
        bmp.Render(canvas)
        enc = PngBitmapEncoder()
        enc.Frames.Add(BitmapFrame.Create(bmp))
        path = os.path.join(OUT_DIR, name + '.png')
        stream = FileStream(path, FileMode.Create)
        enc.Save(stream)
        stream.Close()
        _log.append(u'{} {}x{} children={} -> {}'.format(name, w, h, canvas.Children.Count, path))
    win.Close()
except Exception:
    import traceback
    _log.append(u'EXCEPTION:\n' + unicode(traceback.format_exc()))

RESULT = u'\n'.join(_log)
