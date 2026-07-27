# -*- coding: utf-8 -*-
import os, sys, imp
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow

_logic = imp.load_source('schedpro_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


class _Row(object):
    def __init__(self, d):
        self.mark        = d.get('mark',      u'—')
        self.etype       = d.get('etype',     u'—')
        self.level       = d.get('level',     u'—')
        self.length_m    = d.get('length_m',  u'—')
        self.material    = d.get('material',  u'—')
        self.category    = d.get('category',  u'—')
        self.is_subtotal = bool(d.get('is_subtotal', False))
        for k, v in d.items():
            if k.startswith('ep_'):
                setattr(self, k, v)


class ScheduleProWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'schedule_pro')
        self.doc   = doc
        self._rows = []
        try:
            self.TxtProjectName.Text = doc.ProjectInformation.Name or ''
        except Exception:
            pass
        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

    def _get_selected_cats(self):
        cats = []
        if self.ChkColumns.IsChecked     == True: cats.append('columns')
        if self.ChkBeams.IsChecked       == True: cats.append('beams')
        if self.ChkFoundations.IsChecked == True: cats.append('foundations')
        if self.ChkWalls.IsChecked       == True: cats.append('walls')
        if self.ChkFloors.IsChecked      == True: cats.append('floors')
        return cats or ['columns', 'beams']

    def _get_extra_params(self):
        raw = (self.TxtExtraParams.Text or '').strip()
        if not raw:
            return []
        return [p.strip() for p in raw.split(',') if p.strip()]

    def _get_group_by(self):
        if self.RbGroupLevel.IsChecked    == True: return 'level'
        if self.RbGroupCat.IsChecked      == True: return 'category'
        if self.RbGroupMaterial.IsChecked == True: return 'material'
        return None

    def Run_Click(self, sender, args):
        Vis = System.Windows.Visibility
        self.ProgBar.Visibility = Vis.Visible
        self.BtnRun.IsEnabled   = False
        self.TxtStatus.Text     = u'Collecting elements…'

        cats     = self._get_selected_cats()
        extra    = self._get_extra_params()
        group_by = self._get_group_by()

        try:
            rows = _logic.collect_schedule(self.doc, cats, extra)
            if group_by:
                rows = _logic.subtotals(rows, group_by)
        except Exception as e:
            self.ProgBar.Visibility = Vis.Collapsed
            self.BtnRun.IsEnabled   = True
            self.TxtStatus.Text     = u'Error: {}'.format(e)
            forms.alert(u'Schedule error:\n{}'.format(e))
            return

        self.ProgBar.Visibility = Vis.Collapsed
        self.BtnRun.IsEnabled   = True
        self._rows = rows

        src = ObservableCollection[object]()
        for r in rows:
            src.Add(_Row(r))
        self.GridSchedule.ItemsSource = src

        total = sum(1 for r in rows if not r.get('is_subtotal'))
        self.TxtStatus.Text         = u'{} elements found.'.format(total)
        self.BtnExport.IsEnabled    = total > 0
        self.BtnExportPDF.IsEnabled = total > 0

    def Export_Click(self, sender, args):
        if not self._rows:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            proj  = self.TxtProjectName.Text.strip()
            extra = self._get_extra_params()
            _logic.export_csv(self._rows, path, proj, extra)
            forms.alert(u'Exported:\n{}'.format(path))
        except Exception as e:
            forms.alert(u'Export error:\n{}'.format(e))

    def ExportPDF_Click(self, sender, args):
        if not self._rows:
            return
        import System.Windows.Forms as WinForms
        dlg = WinForms.SaveFileDialog()
        dlg.Filter   = "PDF files (*.pdf)|*.pdf|HTML files (*.html)|*.html|All files (*.*)|*.*"
        dlg.Title    = "Save PDF report"
        dlg.FileName = "structural_schedule.pdf"
        if dlg.ShowDialog() != WinForms.DialogResult.OK:
            return
        path = dlg.FileName
        try:
            proj  = self.TxtProjectName.Text.strip()
            extra = self._get_extra_params()
            out_path, is_pdf = _logic.export_pdf(self._rows, path, proj, extra)
            if is_pdf:
                forms.alert(u'PDF exported:\n{}'.format(out_path))
            else:
                import subprocess
                subprocess.Popen(['start', out_path], shell=True)
                forms.alert(
                    u'Chrome not found — schedule saved as HTML:\n{}\n\n'
                    u'Open in a browser and use File > Print to save as PDF.'.format(out_path))
        except Exception as e:
            forms.alert(u'PDF export error:\n{}'.format(e))

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
