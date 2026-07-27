# -*- coding: utf-8 -*-
"""
QRCode pushbutton – WPF code-behind (unified: generation + titleblock placement).

generate_nosa_qr() returns:
    CPython3   → PIL.Image  (RGBA)          → stream directly to WPF BitmapImage
    IronPython → str (temp PNG file path)   → load from file URI into WPF BitmapImage
"""

import os
import sys

import System.Windows
import System.Windows.Media as Media
import System.Windows.Input as Input

# ---------------------------------------------------------------------------
# Ensure the lib/ folder is on the path (local lib for qr_generator; extension lib for nosa_utils)
# ---------------------------------------------------------------------------
_local_lib = os.path.dirname(__file__)
if _local_lib not in sys.path:
    sys.path.insert(0, _local_lib)

_ext_lib = os.path.abspath(os.path.join(_local_lib, '..', '..', '..', '..', 'lib'))
if _ext_lib not in sys.path:
    sys.path.insert(0, _ext_lib)

import qr_generator   # noqa: E402
from nosa_utils.base_window import NOSAWindow


def _clean_url(url):
    """
    Clean a URL for QR encoding without any external service or redirect.

    For SharePoint/OneDrive sharing links the query string often contains
    long authentication tokens that inflate the QR version.  We strip every
    parameter except 'id' (document path), keeping the base URL intact.
    This is a purely local, offline operation – no network call needed.

    Returns (cleaned_url, True) if the URL was shortened, else (url, False).
    """
    try:
        try:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        except ImportError:
            from urlparse import urlparse, parse_qs, urlunparse  # noqa: F821
            from urllib import urlencode                         # noqa: F821

        parsed = urlparse(url)
        if not parsed.scheme:
            return url, False

        qs = parse_qs(parsed.query, keep_blank_values=True)
        if not qs:
            return url, False   # no query string, already clean

        # Parameters worth keeping (SharePoint direct-link ids)
        KEEP = {'id', 'file', 'source', 'action', 'e', 'cid'}
        qs_clean = {k: v for k, v in qs.items() if k.lower() in KEEP}

        cleaned = urlunparse((
            parsed.scheme, parsed.netloc, parsed.path,
            parsed.params,
            urlencode(qs_clean, doseq=True),
            ''
        ))
        if len(cleaned) < len(url):
            return cleaned, True
    except Exception:
        pass
    return url, False


def _load_tb_logic():
    """
    Execute tb_logic.py directly from source every time.

    Uses compile() + exec() so no .pyc bytecode cache, sys.modules entry,
    or importlib cache is ever consulted.  Works in IronPython 2.7 (.NET 4.8)
    and IronPython 3.x (.NET 8) – both Revit 2024 and 2026/2027.
    """
    import types
    tb_path = os.path.join(_local_lib, 'tb_logic.py')
    mod = types.ModuleType('_tb_logic_live')
    mod.__file__ = tb_path
    if _local_lib not in sys.path:
        sys.path.insert(0, _local_lib)
    with open(tb_path, 'rb') as fh:
        src = fh.read()
    exec(compile(src, tb_path, 'exec'), mod.__dict__)  # noqa: S102
    return mod


# ---------------------------------------------------------------------------
# WPF bitmap helpers
# ---------------------------------------------------------------------------

def _pil_to_wpf_bitmap(pil_img):
    """Stream a PIL RGBA image directly into a WPF BitmapImage (no disk I/O)."""
    import io
    from System.IO import MemoryStream
    from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption

    buf = io.BytesIO()
    pil_img.save(buf, format='PNG')
    data = buf.getvalue()

    ms  = MemoryStream(bytearray(data))
    bmp = BitmapImage()
    bmp.BeginInit()
    bmp.StreamSource  = ms
    bmp.CacheOption   = BitmapCacheOption.OnLoad
    bmp.EndInit()
    bmp.Freeze()
    return bmp


def _path_to_wpf_bitmap(png_path):
    """Load a PNG file into a WPF BitmapImage."""
    from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
    from System import Uri, UriKind

    bmp = BitmapImage()
    bmp.BeginInit()
    bmp.UriSource  = Uri(png_path, UriKind.Absolute)
    bmp.CacheOption = BitmapCacheOption.OnLoad
    bmp.EndInit()
    bmp.Freeze()
    return bmp


def _result_to_wpf_bitmap(result):
    """Accept either a PIL Image or a file path and return a WPF BitmapImage."""
    if isinstance(result, str):
        return _path_to_wpf_bitmap(result)
    return _pil_to_wpf_bitmap(result)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

class QRCodeWindow(NOSAWindow):
    """Main QR Code Generator window (generation + titleblock placement)."""

    def __init__(self, doc=None, uidoc=None):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'qr_code')
        self._doc      = doc    # Revit Document (may be None outside Revit context)
        self._result   = None   # PIL Image or temp PNG path
        self._tmp_path = None   # last temp file (IronPython path); cleaned up on close
        self._restore_last_url()
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def _restore_last_url(self):
        try:
            saved = self.LoadConfig().get('last_url', '')
            if saved:
                self.TxtUrl.Text = saved
        except Exception:
            pass

    def _save_last_url(self, url):
        try:
            cfg = self.LoadConfig()
            cfg['last_url'] = url
            self.SaveConfig(cfg)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_tmp(self):
        if self._tmp_path and os.path.exists(self._tmp_path):
            try:
                os.unlink(self._tmp_path)
            except Exception:
                pass
            self._tmp_path = None

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def TxtUrl_KeyDown(self, sender, args):
        if args.Key == Input.Key.Return:
            self._do_generate()

    def Generate_Click(self, sender, args):
        self._do_generate()

    def Save_Click(self, sender, args):
        if self._result is None:
            return

        import Microsoft.Win32 as Win32

        dlg = Win32.SaveFileDialog()
        dlg.Title      = 'Save NOSA QR Code'
        dlg.Filter     = 'PNG Image (*.png)|*.png'
        dlg.DefaultExt = 'png'
        dlg.FileName   = 'NOSA_QR.png'

        if dlg.ShowDialog() == True:  # noqa: E712
            path = dlg.FileName
            try:
                if isinstance(self._result, str):
                    import shutil
                    shutil.copy(self._result, path)
                else:
                    self._result.save(path, dpi=(300, 300))
                self._set_status(
                    u'\u2713  Saved \u2192 {}'.format(os.path.basename(path)), ok=True
                )
            except Exception as e:
                self._set_status(u'Save failed: {}'.format(e), error=True)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _do_generate(self):
        url = (self.TxtUrl.Text or '').strip()
        if not url or url == 'https://':
            self._set_status('Please enter a URL or text to encode.', error=True)
            return

        self._set_status(u'Generating\u2026')
        self.BtnGenerate.IsEnabled = False
        self._cleanup_tmp()

        try:
            # Clean the URL locally (strip SharePoint tracking params)
            url, was_shortened = _clean_url(url)
            if was_shortened:
                self.TxtUrl.Text = url

            result = qr_generator.generate_nosa_qr(url)

            # Track temp file so we can clean it up later
            if isinstance(result, str):
                self._tmp_path = result
            self._result = result

            bmp = _result_to_wpf_bitmap(result)
            self.PreviewImage.Source     = bmp
            self.PreviewImage.Visibility = System.Windows.Visibility.Visible
            self.RectChecker.Visibility  = System.Windows.Visibility.Visible
            self.TxtPlaceholder.Visibility = System.Windows.Visibility.Collapsed

            self.BtnSave.IsEnabled = True
            if self._doc is not None:
                self.BtnPlaceTB.IsEnabled = True

            short_note = u'  \u2022  URL cleaned (extra parameters removed)' if was_shortened else u''
            self._set_status(
                u'\u2713  Ready  \u2022  24\u00d724 mm  \u2022  1200 dpi  \u2022  2\u00d7 supersampling'
                + short_note,
                ok=True
            )
            self._save_last_url(url)

        except Exception as e:
            self._set_status(u'{}'.format(e), error=True)
        finally:
            self.BtnGenerate.IsEnabled = True

    def PlaceTitleblocks_Click(self, sender, args):
        """Replace the QR in every unique titleblock family in the project."""
        if self._result is None or self._doc is None:
            return

        self.BtnPlaceTB.IsEnabled = False
        self._set_tb_status(u'Updating titleblock families\u2026', ok=False)

        try:
            tb_logic = _load_tb_logic()
            results  = tb_logic.run(self._doc, self._result)

            ok_count   = sum(1 for _, s, _ in results if s == 'ok')
            skip_count = sum(1 for _, s, _ in results if s == 'skip')
            err_count  = sum(1 for _, s, _ in results if s == 'error')

            summary = u'{} updated'.format(ok_count)
            if skip_count:
                summary += u', {} without image (skipped)'.format(skip_count)
            if err_count:
                summary += u', {} error(s)'.format(err_count)
            self._set_tb_status(summary,
                                ok=(err_count == 0 and ok_count > 0),
                                error=(err_count > 0 and ok_count == 0))

            lines = []
            for name, status, msg in results:
                if status == 'ok':
                    icon = u'\u2713'
                elif status == 'skip':
                    icon = u'\u25cb'
                else:
                    icon = u'\u2717'
                detail = u' \u2192 {}'.format(msg) if status == 'error' else u''
                lines.append(u'{}  {}{}'.format(icon, name, detail))
            self._set_status(u'  \u2502  '.join(lines),
                             ok=(err_count == 0 and ok_count > 0))

        except Exception as e:
            self._set_tb_status(u'Error: {}'.format(e), error=True)
        finally:
            self.BtnPlaceTB.IsEnabled = True

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _set_tb_status(self, msg, ok=False, error=False):
        self.TxtTBStatus.Text = msg
        if error:
            self.TxtTBStatus.Foreground = Media.Brushes.Crimson
        elif ok:
            self.TxtTBStatus.Foreground = Media.SolidColorBrush(
                Media.Color.FromRgb(0x22, 0x88, 0x22)
            )
        else:
            self.TxtTBStatus.Foreground = Media.Brushes.DarkOrange

    def _set_status(self, msg, ok=False, error=False):
        self.TxtStatus.Text = msg
        if error:
            self.TxtStatus.Foreground = Media.Brushes.Crimson
        elif ok:
            self.TxtStatus.Foreground = Media.SolidColorBrush(
                Media.Color.FromRgb(0x22, 0x88, 0x22)
            )
        else:
            self.TxtStatus.Foreground = Media.Brushes.Gray

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
