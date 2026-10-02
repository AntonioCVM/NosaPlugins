# -*- coding: utf-8 -*-
"""
Column preset manager dialog — pick, edit, or create a named column preset
for the Sheet Export Hub grid. Built-in presets ("NOSA Protocols") cannot be
overwritten or deleted; "Save as new..." forks the current checklist into an
editable custom preset.
"""
import os
import System
from System.Windows import MessageBox
from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow

import column_presets


class ColumnCheckItem(object):
    def __init__(self, name, checked):
        self.Name = name
        self.IsChecked = checked


class ColumnChooserDialog(NOSAWindow):
    def __init__(self, active_preset_name, available_columns):
        xaml_file = os.path.join(os.path.dirname(__file__), 'column_chooser_dialog.xaml')
        NOSAWindow.__init__(self, xaml_file, 'sheetexporthub_column_chooser')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.ComboPreset.SelectionChanged += self.Preset_Changed
        self.available_columns = list(available_columns)
        self.result_preset_name = None
        self._items = None

        self._load_presets_combo(active_preset_name)
        self._load_checklist(active_preset_name)

    def _load_presets_combo(self, select_name):
        self.ComboPreset.Items.Clear()
        names = column_presets.ColumnPresetManager.get_all_preset_names()
        for n in names:
            self.ComboPreset.Items.Add(n)
        idx = names.index(select_name) if select_name in names else 0
        self.ComboPreset.SelectedIndex = idx

    def _current_preset_name(self):
        return str(self.ComboPreset.SelectedItem) if self.ComboPreset.SelectedItem else None

    def _load_checklist(self, preset_name):
        cols = column_presets.ColumnPresetManager.load_preset(preset_name) or []
        ordered = list(cols) + [c for c in self.available_columns if c not in cols]
        self._items = ObservableCollection[ColumnCheckItem]()
        checked_set = set(cols)
        for name in ordered:
            self._items.Add(ColumnCheckItem(name, name in checked_set))
        self.ListColumns.ItemsSource = self._items

        is_builtin = column_presets.ColumnPresetManager.is_builtin(preset_name)
        self.BtnOverwrite.IsEnabled = not is_builtin
        self.BtnDelete.IsEnabled = not is_builtin
        self.TxtHint.Text = (
            "Built-in preset — use 'Save as new...' to create an editable copy with fewer columns."
            if is_builtin else
            "Custom preset — tick/untick columns, then 'Overwrite preset' to save changes."
        )

    def Preset_Changed(self, sender, args):
        name = self._current_preset_name()
        if name:
            self._load_checklist(name)

    def Overwrite_Click(self, sender, args):
        name = self._current_preset_name()
        if not name or column_presets.ColumnPresetManager.is_builtin(name):
            return
        checked = [i.Name for i in self._items if i.IsChecked]
        if not checked:
            MessageBox.Show("Select at least one column.")
            return
        column_presets.ColumnPresetManager.save_preset(name, checked)
        self.result_preset_name = name
        MessageBox.Show("Preset '{}' updated.".format(name))

    def SaveAsNew_Click(self, sender, args):
        checked = [i.Name for i in self._items if i.IsChecked]
        if not checked:
            MessageBox.Show("Select at least one column.")
            return
        from pyrevit.forms import ask_for_string
        name = ask_for_string(prompt="Enter a name for this new column preset:", title="Save Column Preset")
        if not name:
            return
        name = name.strip()
        if column_presets.ColumnPresetManager.is_builtin(name):
            MessageBox.Show("'{}' is a built-in preset name; choose another.".format(name))
            return
        ok = column_presets.ColumnPresetManager.save_preset(name, checked)
        if ok:
            self.result_preset_name = name
            self._load_presets_combo(name)
            MessageBox.Show("Saved preset '{}'.".format(name))
        else:
            MessageBox.Show("Failed to save preset.")

    def Delete_Click(self, sender, args):
        name = self._current_preset_name()
        if not name or column_presets.ColumnPresetManager.is_builtin(name):
            return
        res = MessageBox.Show(
            "Delete column preset '{}'?".format(name), "Confirm Delete",
            System.Windows.MessageBoxButton.YesNo
        )
        if str(res) == "Yes":
            column_presets.ColumnPresetManager.delete_preset(name)
            self.result_preset_name = column_presets.DEFAULT_PRESET_NAME
            self._load_presets_combo(self.result_preset_name)

    def UseThis_Click(self, sender, args):
        self.result_preset_name = self._current_preset_name()
        self.DialogResult = True
        self.Close()

    def Close_Click(self, sender, args):
        self.DialogResult = bool(self.result_preset_name)
        self.Close()
