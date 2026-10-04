# -*- coding: utf-8 -*-
"""T8.13 — edit the project values of the 0900 General notes and write them to the sheet."""
import os

from Autodesk.Revit import DB
from nosa_utils.base_window import NOSAWindow
from nosa_utils import general_notes as gn
from nosa_utils import transactions as nosa_tx


class GeneralNotesWindow(NOSAWindow):

    def __init__(self, doc):
        NOSAWindow.__init__(self, os.path.join(os.path.dirname(__file__), 'general_notes_window.xaml'),
                            'general_notes')
        self.doc = doc
        self._boxes = {}
        values = gn.defaults()
        values.update(gn.sheet_values(doc))
        values.update(gn.project_values(doc))
        self._build(values)
        if gn.find_view(doc) is None:
            self.BtnApply.IsEnabled = False
            self.TxtStatus.Text = u'No drafting view called "{}" in this model.'.format(gn.VIEW_NAME)

    def _build(self, values):
        from System.Windows import Thickness, FontWeights, GridLength, GridUnitType, VerticalAlignment
        from System.Windows.Controls import Grid, ColumnDefinition, TextBlock, TextBox
        group = None
        for key, label, field_group, _default, _slots in gn.FIELDS:
            if field_group != group:
                group = field_group
                head = TextBlock()
                head.Text = group
                head.FontWeight = FontWeights.Bold
                head.FontSize = 13
                head.Margin = Thickness(0, 12 if self.PanelFields.Children.Count else 0, 0, 4)
                head.SetResourceReference(TextBlock.ForegroundProperty, 'AccentColor')
                self.PanelFields.Children.Add(head)
            row = Grid()
            row.Margin = Thickness(0, 2, 0, 2)
            for width in (GridLength(1, GridUnitType.Star), GridLength(180)):
                col = ColumnDefinition()
                col.Width = width
                row.ColumnDefinitions.Add(col)
            text = TextBlock()
            text.Text = label
            text.VerticalAlignment = VerticalAlignment.Center
            text.SetResourceReference(TextBlock.ForegroundProperty, 'TextColor')
            box = TextBox()
            box.Text = values.get(key) or u''
            box.ToolTip = gn.param_name(key)
            Grid.SetColumn(box, 1)
            row.Children.Add(text)
            row.Children.Add(box)
            self.PanelFields.Children.Add(row)
            self._boxes[key] = box

    def values(self):
        return dict((k, b.Text) for k, b in self._boxes.items() if b.Text.strip())

    def Apply_Click(self, sender, args):
        report = gn.bind(self.doc)
        if report.get('errors'):
            self.TxtStatus.Text = u'Could not add the parameters: {}'.format(u'; '.join(report['errors'][:3]))
            return
        values = self.values()
        t = nosa_tx.guard(DB.Transaction(self.doc, u'NOSA — General Notes (0900)'))
        t.Start()
        try:
            gn.write_project_values(self.doc, values)
            changed, missing = gn.apply(self.doc, values)
        except Exception as e:
            t.RollBack()
            self.TxtStatus.Text = u'Not applied: {}'.format(e)
            return
        t.Commit()
        msg = u'{} value(s) saved in Project Information; {} change(s) written on 0900.'.format(len(values), changed)
        if missing:
            msg += u' Not found on the sheet (wording changed?): {}.'.format(u', '.join(missing))
        self.TxtStatus.Text = msg

    def Close_Click(self, sender, args):
        self.Close()
