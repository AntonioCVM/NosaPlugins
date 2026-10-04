# -*- coding: utf-8 -*-
"""RebarAutomate — Partitions dialog (T7.1); opened from Revit's API context."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_lib = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.bootstrap import load_module
from nosa_utils.telemetry import log_swallowed
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs
_LOG = u'rebarautomate'

rebar_partitions = load_module('rebar_partitions', os.path.join(_HERE, 'rebar_partitions.py'))

_CATEGORY_LABELS = {
    u'OST_StructuralColumns': u'Column',
    u'OST_StructuralFraming': u'Beam',
    u'OST_StructuralFoundation': u'Foundation',
    u'OST_Floors': u'Slab',
    u'OST_Walls': u'Wall',
}


class PartitionRow(object):
    def __init__(self, host):
        self.host = host
        self.HostId = host['id']
        self.Category = _CATEGORY_LABELS.get(host['category'], u'Other')
        self.TypeName = host['type']
        self.HostMark = host['mark']
        self.Level = host['level']
        self.Bars = host['bars']
        self.Partition = u''
        self.Members = 1
        self.Group = 0
        self.Scheduled = u'Yes'
        self.representative = True


class PartitionsWindow(NOSAWindow):
    def __init__(self, doc, ctx):
        NOSAWindow.__init__(self, os.path.join(_HERE, 'partitions.xaml'), 'rebarautomate_partitions')
        self.doc = doc
        self.ctx = ctx
        self.summary = None
        self.hosts = rebar_partitions.collect_hosts(doc)
        self.rows = [PartitionRow(h) for h in self.hosts]
        self._plan(rename=True)

    def _plan(self, rename):
        """Regroup; rename=False keeps the names typed by the user (first row of each group wins)."""
        group = bool(self.ChkGroupIdentical.IsChecked)
        assignment = rebar_partitions.plan(self.hosts, group_identical=group)
        typed = {}
        if not rename:
            for row in self.rows:
                typed.setdefault(assignment[row.HostId]['group'], row.Partition)
        for row in self.rows:
            entry = assignment[row.HostId]
            row.Partition = typed.get(entry['group']) or entry['partition']
            row.Group = entry['group']
            row.Members = entry['members']
            row.representative = entry['representative']
            row.Scheduled = u'Yes' if entry['representative'] else u'No (copy)'
        self.rows.sort(key=lambda r: (r.Group, not r.representative, r.HostId))
        self.GridHosts.ItemsSource = None
        self.GridHosts.ItemsSource = self.rows
        groups = len(set(r.Group for r in self.rows))
        self.TxtSummary.Text = (u'{} reinforced host(s) in {} partition(s); {} identical copy(ies) '
                                u'counted through No. of mbrs.'.format(
                                    len(self.rows), groups, len(self.rows) - groups))

    def GroupIdentical_Click(self, sender, args):
        self._plan(rename=False)

    def AutoName_Click(self, sender, args):
        self._plan(rename=True)

    def GridHosts_CellEditEnding(self, sender, args):
        """A new name applies to the whole group: identical hosts share one partition."""
        try:
            row = args.Row.Item
            text = (getattr(args.EditingElement, 'Text', u'') or u'').strip()
            if not text:
                return
            for other in self.rows:
                if other.Group == row.Group:
                    other.Partition = text
            self.Dispatcher.BeginInvoke(System_Action(self._refresh_grid))
        except Exception:
            log_swallowed(_LOG, u'GridHosts_CellEditEnding')

    def _refresh_grid(self):
        try:
            self.GridHosts.Items.Refresh()
        except Exception:
            log_swallowed(_LOG, u'partitions refresh')

    def Cancel_Click(self, sender, args):
        self.Close()

    def Apply_Click(self, sender, args):
        from pyrevit import forms, revit
        assignment = {}
        for row in self.rows:
            if not row.Partition:
                forms.alert(u'Every host needs a partition name.', title=u'RebarAutomate — Partitions')
                return
            assignment[row.HostId] = {'partition': row.Partition, 'group': row.Group,
                                      'members': row.Members, 'representative': row.representative}
        with nosa_tx.revit_transaction(u'NOSA — Partitions'):
            self.summary = rebar_partitions.apply(self.doc, self.hosts, assignment, self.ctx)
        self.Close()


def System_Action(fn):
    import System
    return System.Action(fn)
