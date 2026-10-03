# -*- coding: utf-8 -*-
"""
Pre-export confirmation — shows the exact output filename for every
sheet/view x format combination before anything touches disk, plus any
warnings from ExportValidator (duplicate names, files that will be
overwritten, disk space / permission issues).

Filenames are shown exactly as the exporter will use them — no invented
auto-numbering: Export Sheets Pro's exporters.py does not rename
collisions, it overwrites, so two identical rows here means two files
will genuinely collide. The warning banner above the table says so.
"""
import os
import System
from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow

from validation import ExportValidator


class FileRow(object):
    def __init__(self, type_label, item, output_file):
        self.Type = type_label
        self.Item = item
        self.OutputFile = output_file


class ConfirmExportDialog(NOSAWindow):
    def __init__(self, elements, naming_builder, export_formats, output_folder,
                 project_params, is_views):
        xaml_file = os.path.join(os.path.dirname(__file__), 'confirm_export_dialog.xaml')
        NOSAWindow.__init__(self, xaml_file, 'sheetexporthub_confirm_export')

        rows = self._build_file_rows(elements, naming_builder, export_formats, is_views, project_params)
        collection = ObservableCollection[FileRow]()
        for r in rows:
            collection.Add(r)
        self.GridFiles.ItemsSource = collection

        self.TxtTitle.Text = "{} item(s) ready to export".format(len(elements))
        fmt_names = [f for f in ('pdf', 'dwg', 'dxf') if export_formats.get(f)]
        self.TxtSubtitle.Text = "Formats: {}   ·   Destination: {}".format(
            " + ".join(f.upper() for f in fmt_names) or "none", output_folder
        )

        validator = ExportValidator()
        validator.validate(elements, naming_builder, output_folder, export_formats,
                            is_views=is_views, project_params=project_params)
        summary = validator.get_summary()
        warnings = list(summary.get('warning_list', [])) + list(summary.get('error_list', []))
        if warnings:
            self.WarningsBox.Visibility = System.Windows.Visibility.Visible
            self.ListWarnings.ItemsSource = ["• " + w for w in warnings]

        self.BtnExport.IsEnabled = summary.get('valid', True)

    def _build_file_rows(self, elements, naming_builder, export_formats, is_views, project_params):
        rows = []
        type_label = "View" if is_views else "Sheet"
        formats = [f for f in ('pdf', 'dwg', 'dxf') if export_formats.get(f)]
        for el in elements:
            try:
                base_name = naming_builder.build_filename(el, project_params=project_params, is_view=is_views)
            except Exception:
                base_name = getattr(el, 'Name', str(el.Id))
            if hasattr(el, 'SheetNumber'):
                item_label = "{} - {}".format(el.SheetNumber, el.Name)
            else:
                item_label = el.Name
            for ext in formats:
                rows.append(FileRow(type_label, item_label, "{}.{}".format(base_name, ext)))
        return rows

    def Export_Click(self, sender, args):
        self.DialogResult = True
        self.Close()

    def Cancel_Click(self, sender, args):
        self.DialogResult = False
        self.Close()
