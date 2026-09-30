# -*- coding: utf-8 -*-
import imp
import os
import sys

from System.Collections.ObjectModel import ObservableCollection

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
_logic = imp.load_source('centerbeam_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))


class PreviewRow(object):
    def __init__(self, element, end, column, distance, action):
        self.Element  = _logic.element_label(element)
        self.ElemId   = u"{}".format(element.Id)
        self.End      = end
        self.Column   = column
        self.Distance = distance
        self.Action   = action
        self.is_skip  = action != u"Align"


class CenterBeamToColumnWindow(NOSAWindow):

    def __init__(self, doc, elements=None):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'center_beam_to_column')
        self.doc = doc
        self._is_loaded = False
        self._plan = ([], [], [])

        if elements is None:
            from pyrevit import revit
            elements = revit.get_selection()
        self._sel = _logic.classify_selection(elements)
        if not self._validate_selection():
            self._init_ok = False
            return

        cfg = _logic.DEFAULT_CONFIG.copy()
        cfg.update(self.LoadConfig())
        self._cfg = cfg
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)
        self.TxtMaxDistance.Text = u"{}".format(cfg.get('max_distance_mm', 1000))

        has_beams = bool(self._sel['beams'] or self._sel['ground_beams'])
        self.ChkBothEnds.IsChecked = bool(cfg.get('align_both_ends', True))
        self.ChkBothEnds.IsEnabled = has_beams

        self.TxtBeams.Text       = u"{}".format(len(self._sel['beams']))
        self.TxtGroundBeams.Text = u"{}".format(len(self._sel['ground_beams']))
        self.TxtPilecaps.Text    = u"{}".format(len(self._sel['pilecaps']))
        self.TxtColumns.Text     = u"{}".format(len(self._sel['columns']))

        self._rows = ObservableCollection[PreviewRow]()
        self.GridPreview.ItemsSource = self._rows

        self.ChkBothEnds.Click += self.Options_Changed
        self.TxtMaxDistance.TextChanged += self.Options_Changed
        self._is_loaded = True
        self._refresh_preview()

    # ── selection ────────────────────────────────────────────────────────────

    def _validate_selection(self):
        from pyrevit import forms
        s = self._sel
        has_elements = s['beams'] or s['ground_beams'] or s['pilecaps']
        if not has_elements and not s['columns']:
            forms.alert(
                u"No elements selected.\n\n"
                u"Please select:\n"
                u"- Beams AND/OR Pilecaps\n"
                u"- AND at least one Column",
                title=u"Selection Required")
            return False
        if not has_elements:
            forms.alert(
                u"No beams or pilecaps selected.\n\n"
                u"Selected columns: {}\n"
                u"Please also select beams/ground beams or pilecaps.".format(len(s['columns'])),
                title=u"Elements Required")
            return False
        if not s['columns']:
            forms.alert(
                u"No columns selected.\n\n"
                u"Selected beams: {}\n"
                u"Selected ground beams: {}\n"
                u"Selected pilecaps: {}\n"
                u"Please also select at least one column.".format(
                    len(s['beams']), len(s['ground_beams']), len(s['pilecaps'])),
                title=u"Columns Required")
            return False
        return True

    # ── options / preview ────────────────────────────────────────────────────

    def _read_max_distance(self):
        try:
            value = float(self.TxtMaxDistance.Text.strip())
        except (ValueError, AttributeError):
            return None
        if value <= 0:
            return None
        return int(value) if value == int(value) else value

    def _align_both(self):
        return self.ChkBothEnds.IsChecked == True

    def Options_Changed(self, sender, args):
        if not self._is_loaded:
            return
        self._refresh_preview()

    def _refresh_preview(self):
        self._rows.Clear()
        max_mm = self._read_max_distance()
        if max_mm is None:
            self._plan = ([], [], [])
            self.TxtSummary.Text = u"Enter a maximum distance greater than 0 mm."
            self.BtnAlign.IsEnabled = False
            return

        beam_al, pile_al, skipped = _logic.plan_alignments(
            self._sel, self._align_both(), max_mm)
        self._plan = (beam_al, pile_al, skipped)

        for a in beam_al:
            self._rows.Add(PreviewRow(
                a['beam'], u"{}".format(a['end_index']), u"{}".format(a['column'].Id),
                u"{:.0f}".format(a['distance_mm']), u"Align"))
        for a in pile_al:
            self._rows.Add(PreviewRow(
                a['pilecap'], u"–", u"{}".format(a['column'].Id),
                u"{:.0f}".format(a['distance_mm']), u"Align"))
        for elem, reason in skipped:
            self._rows.Add(PreviewRow(elem, u"–", u"–", u"–", u"Skipped: {}".format(reason)))

        total = len(beam_al) + len(pile_al)
        if total == 0:
            self.TxtSummary.Text = (u"No elements to align. All elements are either "
                                    u"already aligned or too far from columns.")
        else:
            self.TxtSummary.Text = (u"{} to align (beam/ground beam ends: {}, pilecaps: {}) · "
                                    u"{} skipped".format(total, len(beam_al), len(pile_al), len(skipped)))
        self.BtnAlign.IsEnabled = total > 0

    # ── actions ──────────────────────────────────────────────────────────────

    def _save_options(self):
        cfg = self.LoadConfig()
        for key, value in self._cfg.items():
            cfg.setdefault(key, value)
        cfg['align_both_ends'] = self._align_both()
        max_mm = self._read_max_distance()
        if max_mm is not None:
            cfg['max_distance_mm'] = max_mm
        self.SaveConfig(cfg)

    def Align_Click(self, sender, args):
        from pyrevit import forms
        beam_al, pile_al, skipped = self._plan
        if not (beam_al or pile_al):
            return
        self._save_options()
        self.SetLoading(True, u"Aligning elements...")
        try:
            res = _logic.execute_alignments(self.doc, beam_al, pile_al)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u"Alignment failed:\n{}".format(e), title=u"NOSA — Align Element to Column")
            return
        self.SetLoading(False)
        self.Close()
        self._report(res, len(skipped))

    def Cancel_Click(self, sender, args):
        self._save_options()
        self.Close()

    def _report(self, res, skipped_count):
        from pyrevit import forms, script
        from nosa_utils import ui_helpers
        output = script.get_output()
        output.print_md(u"## Align Element to Column")
        output.print_md(u"### Processing...")
        for line in res['log']:
            output.print_md(line)
        output.print_md(u"---")
        output.print_md(u"## ✅ Alignment Complete")
        ui_helpers.display_results(u"Results", {
            u"Beams Aligned": res['beams'],
            u"Ground Beams Aligned": res['ground_beams'],
            u"Pilecaps Aligned": res['pilecaps'],
            u"Failed": res['failed'],
            u"Skipped": skipped_count,
        })
        if res['warnings']:
            output.print_md(u"### Warnings")
            for warning in res['warnings']:
                output.print_md(u"- {}".format(warning))

        forms.alert(
            u"Alignment Complete!\n\n"
            u"✓ Beams: {}\n"
            u"✓ Ground beams: {}\n"
            u"✓ Pilecaps: {}\n"
            u"✗ Failed: {}\n"
            u"⊘ Skipped: {}".format(res['beams'], res['ground_beams'], res['pilecaps'],
                                    res['failed'], skipped_count),
            title=u"Alignment Complete")
