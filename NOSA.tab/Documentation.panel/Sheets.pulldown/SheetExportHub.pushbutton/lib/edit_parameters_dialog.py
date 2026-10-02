# -*- coding: utf-8 -*-
"""
Batch parameter edit dialog — apply one value per parameter to every
currently-selected sheet/view in a single go. Blank field = don't change
that parameter. The actual write (single Transaction) happens back in
ui.py via param_editor.apply_changes, so there is exactly one write path
shared with the inline cell-edit flow.
"""
import os
from System.Collections.ObjectModel import ObservableCollection
from nosa_utils.base_window import NOSAWindow


class FieldInputItem(object):
    def __init__(self, name):
        self.Name = name
        self.Value = ""


class EditParametersDialog(NOSAWindow):
    def __init__(self, editable_fields, selected_count):
        xaml_file = os.path.join(os.path.dirname(__file__), 'edit_parameters_dialog.xaml')
        NOSAWindow.__init__(self, xaml_file, 'sheetexporthub_edit_parameters')

        self.result_values = None

        self._fields = ObservableCollection[FieldInputItem]()
        for name in editable_fields:
            self._fields.Add(FieldInputItem(name))
        self.ListFields.ItemsSource = self._fields

        self.TxtSubtitle.Text = (
            "Editing {} selected item(s) — fields left blank are not changed."
            .format(selected_count)
        )

    def Apply_Click(self, sender, args):
        values = {}
        for item in self._fields:
            v = (item.Value or "").strip()
            if v:
                values[item.Name] = v
        if not values:
            from System.Windows import MessageBox
            MessageBox.Show("Fill in at least one field, or Cancel.")
            return
        self.result_values = values
        self.DialogResult = True
        self.Close()

    def Cancel_Click(self, sender, args):
        self.DialogResult = False
        self.Close()
