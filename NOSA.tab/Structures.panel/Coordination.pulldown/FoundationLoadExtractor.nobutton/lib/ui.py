# -*- coding: utf-8 -*-
import imp
import os, sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('foundload_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class _Row(object):
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


class FoundationLoadWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'foundation_loads')
        self.doc   = doc
        self._rows = []
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility = Vis.Visible
        self.BtnRun.IsEnabled   = False

        try:
            rows = _logic.get_foundation_loads(self.doc)
        except Exception as e:
            self.ProgBar.Visibility = Vis.Collapsed
            self.BtnRun.IsEnabled   = True
            forms.alert(u'Error extracting loads:\n{}'.format(e))
            return

        self.ProgBar.Visibility = Vis.Collapsed
        self.BtnRun.IsEnabled   = True
        self._rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.GridLoads.ItemsSource = src

        no_data = sum(1 for r in rows if r.get('N_kN') == u'—')
        self.TxtStatus.Text = (
            u'{} foundations found. {} with analytical reactions; {} without.'.format(
                len(rows), len(rows) - no_data, no_data))
        self.BtnExport.IsEnabled    = bool(rows)
        self.BtnSelect.IsEnabled    = bool(rows)
        self.BtnExportPDF.IsEnabled = bool(rows)

    def Select_Click(self, sender, args):
        if not self._rows:
            return
        try:
            from System import Int64
            ids = List[DB.ElementId]([
                DB.ElementId(Int64(int(r['id']))) for r in self._rows
            ])
            revit.uidoc.Selection.SetElementIds(ids)
            self.TxtStatus.Text = u'{} element(s) selected.'.format(len(ids))
        except Exception as e:
            forms.alert(u'Error selecting: {}'.format(e))

    def Export_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            _logic.export_csv(self._rows, path)
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Error exporting: {}'.format(e))

    def ExportPDF_Click(self, sender, args):
        if not self._rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.SaveFileDialog()
        dlg.Filter   = "PDF files (*.pdf)|*.pdf|HTML files (*.html)|*.html|All files (*.*)|*.*"
        dlg.Title    = "Save foundation load report"
        dlg.FileName = "foundation_load_report.pdf"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        try:
            proj = ''
            try:
                proj = self.doc.ProjectInformation.Name or ''
            except Exception:
                pass
            out_path, is_pdf = _logic.export_pdf_report(self._rows, dlg.FileName, proj)
            if is_pdf:
                forms.alert(u'PDF report exported:\n{}'.format(out_path))
            else:
                import subprocess
                subprocess.Popen(['start', out_path], shell=True)
                forms.alert(
                    u'Chrome not found — report saved as HTML:\n{}\n\n'
                    u'Open in a browser and use File > Print to save as PDF.'.format(out_path))
        except Exception as e:
            forms.alert(u'PDF export error:\n{}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
