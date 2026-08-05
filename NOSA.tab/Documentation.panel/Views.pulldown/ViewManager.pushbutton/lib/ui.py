# -*- coding: utf-8 -*-
import imp
import os
import sys

from Autodesk.Revit import DB

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value
from nosa_utils import unit_conversion as _uc10

_logic = imp.load_source('viewmanager_logic',
                         os.path.join(os.path.dirname(__file__), 'logic.py'))


def _load_sibling_logic(name, module_name):
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    for suffix in ('pushbutton', 'nobutton'):
        path = os.path.join(base, '{}.{}'.format(name, suffix), 'lib', 'logic.py')
        if os.path.exists(path):
            return imp.load_source(module_name, path)
    raise ImportError('Cannot find logic for: ' + name)


_vbm = _load_sibling_logic('ViewBatchManager', 'viewmanager_vbm')

_NO_TEMPLATE = u'(no template)'


class LevelItem(object):
    def __init__(self, lid, name, elev_ft):
        self.IsChecked = False
        self.Label     = u'{}  ({:+.2f} m)'.format(name, elev_ft * _uc10.FT_TO_M)
        self.LevelId   = lid


class ViewRow(object):
    def __init__(self, rec, new_name=u''):
        self.ViewName = rec['name']
        self.ViewKind = rec['type']
        self.Template = rec['template']
        self.NewName  = new_name
        self.OnSheet  = u''
        self.DetailNo = u''
        self._rec     = rec


class CleanRow(object):
    def __init__(self, rec):
        self.ViewName = rec['name']
        self.ViewKind = rec['type']
        self._rec     = rec


class ViewManagerWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_manager')
        self.doc = doc
        self._tabs = {
            'BtnTabCreate':    self.TabCreate,
            'BtnTabDuplicate': self.TabDuplicate,
            'BtnTabRename':    self.TabRename,
            'BtnTabTemplates': self.TabTemplates,
            'BtnTabProps':     self.TabProps,
            'BtnTabClean':     self.TabClean,
        }
        self._all_views = []
        self._templates = []
        self._clean_loaded = False
        self._rename_name_pending = {}    # {view_id_int: manual new-name text}
        self._rename_detail_pending = {}  # {view_id_int: manual detail-number text}

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self.CmbRenCase.Items.Add(u'Title Case')
        self.CmbRenCase.Items.Add(u'UPPERCASE')
        self.CmbRenCase.Items.Add(u'lowercase')
        self.CmbRenCase.Items.Add(u'Sentence case')
        self.CmbRenCase.SelectedIndex = 0

        for d in (u'Coarse', u'Medium', u'Fine'):
            self.CmbPropDetail.Items.Add(d)
        self.CmbPropDetail.SelectedIndex = 1
        for d in (u'Structural', u'Architectural', u'Coordination',
                  u'Mechanical', u'Electrical', u'Plumbing'):
            self.CmbPropDisc.Items.Add(d)
        self.CmbPropDisc.SelectedIndex = 0

        self._load_all()

    # ── data ──────────────────────────────────────────────────────────────────

    def _load_all(self):
        # Levels
        levels = _logic.get_levels(self.doc)
        self.ListLevels.ItemsSource = [LevelItem(lid, name, el) for lid, name, el in levels]

        # View family types
        self._vfts = _logic.get_plan_view_family_types(self.doc)
        self.CmbCreateType.Items.Clear()
        for _, label in self._vfts:
            self.CmbCreateType.Items.Add(label)
        if self._vfts:
            self.CmbCreateType.SelectedIndex = 0

        # Templates — every template in the project, any view type
        self._templates = _logic.get_all_view_templates(self.doc)
        for combo in (self.CmbCreateTemplate, self.CmbTplApply):
            combo.Items.Clear()
            combo.Items.Add(_NO_TEMPLATE)
            for _, name in self._templates:
                combo.Items.Add(name)
            combo.SelectedIndex = 0

        # Views (shared by Duplicate / Rename / Templates tabs)
        self._sheet_map = _logic.sheet_map(self.doc)
        self._all_views = _vbm.collect_views(self.doc)
        self._refresh_dup()
        self._refresh_rename()
        self._refresh_tpl()
        self._refresh_props()

        self.TxtSummary.Text = u'{} views · {} levels · {} templates'.format(
            len(self._all_views), len(levels), len(self._templates))
        self.TxtStatus.Text = u'Ready.'

    def _filtered_views(self, search_box):
        try:
            text = (search_box.Text or u'').strip().lower()
        except Exception:
            text = u''
        rows = self._all_views
        if text:
            rows = [r for r in rows
                    if text in r['name'].lower()
                    or text in r['type'].lower()
                    or text in r['template'].lower()]
        return rows

    def _make_row(self, rec, new_name=u''):
        row = ViewRow(rec, new_name)
        try:
            info = self._sheet_map.get(get_id_value(rec['id']))
            if info:
                row.OnSheet  = info.get('sheet', u'')
                row.DetailNo = info.get('detail', u'')
        except Exception:
            pass
        return row

    def _refresh_dup(self):
        self.GridDupViews.ItemsSource = [
            self._make_row(r) for r in self._filtered_views(self.TxtDupSearch)]

    def _refresh_tpl(self):
        self.GridTplViews.ItemsSource = [
            self._make_row(r) for r in self._filtered_views(self.TxtTplSearch)]

    def _refresh_props(self):
        self.GridPropViews.ItemsSource = [
            self._make_row(r) for r in self._filtered_views(self.TxtPropSearch)]

    def _rename_params(self):
        if self.RbRenPS.IsChecked:
            return 'prefix_suffix', {
                'prefix': self.TxtRenPrefix.Text or u'',
                'suffix': self.TxtRenSuffix.Text or u'',
            }
        if self.RbRenCase.IsChecked:
            modes = {0: 'title', 1: 'upper', 2: 'lower', 3: 'sentence'}
            return 'case', {'case_mode': modes.get(self.CmbRenCase.SelectedIndex, 'title')}
        return 'find_replace', {
            'find':    self.TxtRenFind.Text or u'',
            'replace': self.TxtRenReplace.Text or u'',
        }

    def _refresh_rename(self):
        """Populate the grid's single 'Name' cell with the effective value —
        the view's current name unless a rule or a manual edit changes it —
        so the cell is always directly editable in place, the same way the
        'No.' (detail number) cell already works."""
        mode, params = self._rename_params()
        rows = []
        for r in self._filtered_views(self.TxtRenSearch):
            vid = get_id_value(r['id'])
            if vid in self._rename_name_pending:
                new = self._rename_name_pending[vid]
            else:
                new = _vbm.compute_new_name(r['name'], mode, params)
            row = self._make_row(r, new)
            if vid in self._rename_detail_pending:
                row.DetailNo = self._rename_detail_pending[vid]
            rows.append(row)
        self.GridRename.ItemsSource = rows

    def Rename_CellEdit(self, sender, args):
        """Track direct typing into the 'Name' / 'No.' columns so manual
        edits survive rule changes and search re-filtering."""
        try:
            row = args.Row.Item
            header = str(getattr(args.Column, 'Header', ''))
            if header not in ('Name', 'No.'):
                return
            txt = args.EditingElement.Text \
                if hasattr(args.EditingElement, 'Text') else ''
            vid = get_id_value(row._rec['id'])
            if header == 'Name':
                row.NewName = u'{}'.format(txt)
                self._rename_name_pending[vid] = row.NewName
            else:
                row.DetailNo = u'{}'.format(txt)
                self._rename_detail_pending[vid] = row.DetailNo
        except Exception:
            pass

    def _refresh_clean(self):
        self.GridClean.ItemsSource = [
            CleanRow(r) for r in _logic.unplaced_views(self.doc)]
        self._clean_loaded = True

    # ── tab switching ─────────────────────────────────────────────────────────

    def Tab_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._tabs)
        if sender.Name == 'BtnTabClean' and not self._clean_loaded:
            self._refresh_clean()

    # ── create tab ────────────────────────────────────────────────────────────

    def CreateViews_Click(self, sender, args):
        from pyrevit import forms
        level_ids = [it.LevelId for it in (self.ListLevels.ItemsSource or [])
                     if it.IsChecked]
        if not level_ids:
            forms.alert(u'Tick at least one level.')
            return
        idx = self.CmbCreateType.SelectedIndex
        if idx < 0 or idx >= len(self._vfts):
            forms.alert(u'Select a view family type.')
            return
        vft_id = self._vfts[idx][0]

        template_id = DB.ElementId.InvalidElementId
        t_idx = self.CmbCreateTemplate.SelectedIndex
        if t_idx > 0:
            template_id = self._templates[t_idx - 1][0]

        try:
            scale = int(self.TxtCreateScale.Text.strip())
        except Exception:
            scale = None

        pattern = self.TxtCreatePattern.Text or u'{level}'
        if not forms.alert(u'Create {} view(s)?'.format(len(level_ids)),
                           yes=True, no=True):
            return

        self.SetLoading(True, u'Creating views…')
        try:
            created, failed, errors = _logic.create_plan_views(
                self.doc, level_ids, vft_id, pattern, template_id, scale)
        finally:
            self.SetLoading(False)

        self.TxtStatus.Text = u'Created {} view(s). Failed: {}.'.format(created, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'View Manager — errors')
        self._load_all()

    def Create3D_Click(self, sender, args):
        from pyrevit import forms
        if not forms.alert(u'Create one section-boxed 3D view per level?',
                           yes=True, no=True):
            return
        self.SetLoading(True, u'Creating 3D views…')
        try:
            created, failed, errors = _logic.create_3d_per_level(self.doc)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'3D views created: {}  ·  Failed: {}'.format(created, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'View Manager — errors')
        self._load_all()

    def CreateDrafting_Click(self, sender, args):
        from pyrevit import forms
        try:
            count = max(1, int(self.TxtDraftCount.Text.strip()))
        except Exception:
            count = 1
        try:
            scale = int(self.TxtCreateScale.Text.strip())
        except Exception:
            scale = None
        self.SetLoading(True, u'Creating drafting views…')
        try:
            created, failed, errors = _logic.create_drafting_views(
                self.doc, count, scale=scale)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Drafting views created: {}  ·  Failed: {}'.format(created, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'View Manager — errors')
        self._load_all()

    # ── duplicate tab ─────────────────────────────────────────────────────────

    def DupSearch_Changed(self, sender, args):
        self._refresh_dup()

    def Preview_Click(self, sender, args):
        from pyrevit import forms
        row = self.GridDupViews.SelectedItem
        if row is None:
            forms.alert(u'Highlight one view in the list first.')
            return
        view = self.doc.GetElement(row._rec['id'])
        if view is None:
            return
        import tempfile
        folder = os.path.join(tempfile.gettempdir(), 'nosa_view_previews')
        self.SetLoading(True, u'Exporting preview…')
        try:
            path = _logic.export_view_preview(self.doc, view, folder)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Preview failed: {}'.format(e))
            return
        self.SetLoading(False)
        if path and os.path.isfile(path):
            try:
                os.startfile(path)
                self.TxtStatus.Text = u'Preview opened: {}'.format(os.path.basename(path))
            except Exception:
                self.TxtStatus.Text = u'Preview saved: {}'.format(path)
        else:
            self.TxtStatus.Text = u'No preview image was produced.'

    def Duplicate_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridDupViews.SelectedItems or [])
        if not rows:
            forms.alert(u'Select at least one view in the list.')
            return
        if self.RbDupDetail.IsChecked:
            mode = 'with_detailing'
        elif self.RbDupDependent.IsChecked:
            mode = 'dependent'
        else:
            mode = 'duplicate'
        try:
            copies = max(1, int(self.TxtDupCopies.Text.strip()))
        except Exception:
            copies = 1
        pattern = self.TxtDupPattern.Text or u'{name} - Copy {n}'

        if not forms.alert(u'Duplicate {} view(s) × {} cop{}?'.format(
                len(rows), copies, u'ies' if copies != 1 else u'y'),
                yes=True, no=True):
            return

        ids = [r._rec['id'] for r in rows]
        self.SetLoading(True, u'Duplicating views…')
        try:
            created, skipped, failed, errors = _logic.duplicate_views(
                self.doc, ids, mode, copies, pattern)
        finally:
            self.SetLoading(False)

        self.TxtStatus.Text = u'Duplicated: {}  ·  Skipped: {}  ·  Failed: {}'.format(
            created, skipped, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'View Manager — warnings')
        self._load_all()

    # ── rename tab ────────────────────────────────────────────────────────────

    def RenameRule_Changed(self, sender, args):
        try:
            self._refresh_rename()
        except Exception:
            pass

    def Rename_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridRename.SelectedItems or [])
        if not rows:
            rows = list(self.GridRename.ItemsSource or [])
        renames = [(r._rec['id'], r.NewName) for r in rows
                   if r.NewName and r.NewName != r._rec['name']]
        detail_updates = [
            (r._rec['id'], r.DetailNo) for r in rows
            if get_id_value(r._rec['id']) in self._rename_detail_pending]
        if not renames and not detail_updates:
            forms.alert(u'No changes to apply — type into "Name" or "No." first.')
            return
        parts = []
        if renames:
            parts.append(u'{} name(s)'.format(len(renames)))
        if detail_updates:
            parts.append(u'{} detail number(s)'.format(len(detail_updates)))
        if not forms.alert(u'Apply {}?'.format(u' and '.join(parts)),
                           yes=True, no=True):
            return
        self.SetLoading(True, u'Applying changes…')
        try:
            ok = failed = 0
            if renames:
                ok, failed = _vbm.rename_views(self.doc, renames)
            det_ok = det_failed = 0
            det_errors = []
            if detail_updates:
                det_ok, det_failed, det_errors = _logic.set_detail_numbers(
                    self.doc, detail_updates)
        finally:
            self.SetLoading(False)
        for r in rows:
            vid = get_id_value(r._rec['id'])
            self._rename_name_pending.pop(vid, None)
            self._rename_detail_pending.pop(vid, None)
        self.TxtStatus.Text = u'Renamed: {} ok / {} failed.  Detail #: {} ok / {} failed.'.format(
            ok, failed, det_ok, det_failed)
        if det_errors:
            forms.alert(u'\n'.join(det_errors[:8]), title=u'View Manager — detail number warnings')
        self._load_all()

    # ── templates tab ─────────────────────────────────────────────────────────

    def TplSearch_Changed(self, sender, args):
        self._refresh_tpl()

    def _apply_template_id(self, template_id, label):
        from pyrevit import forms
        rows = list(self.GridTplViews.SelectedItems or [])
        used_all = False
        if not rows:
            rows = list(self.GridTplViews.ItemsSource or [])
            used_all = True
        if not rows:
            forms.alert(u'No views listed — adjust the search filter.')
            return
        if used_all and not forms.alert(
                u'No rows highlighted — apply to all {} listed view(s)?'.format(len(rows)),
                yes=True, no=True):
            return
        ids = [r._rec['id'] for r in rows]
        self.SetLoading(True, u'Updating templates…')
        try:
            ok, failed = _vbm.apply_view_template(self.doc, ids, template_id)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'{}: {} ok, {} failed.'.format(label, ok, failed)
        self._all_views = _vbm.collect_views(self.doc)
        self._refresh_tpl()
        self._refresh_dup()

    def ApplyTemplate_Click(self, sender, args):
        from pyrevit import forms
        if not self._templates:
            forms.alert(u'This project has no view templates. Create one in '
                        u'Revit (View > View Templates) first.')
            return
        idx = self.CmbTplApply.SelectedIndex
        if idx <= 0:
            forms.alert(u'Pick a template in the "Template to apply" dropdown first.')
            return
        self._apply_template_id(self._templates[idx - 1][0], u'Template applied')

    def RemoveTemplate_Click(self, sender, args):
        self._apply_template_id(DB.ElementId.InvalidElementId, u'Template removed')

    # ── properties tab ────────────────────────────────────────────────────────

    def PropSearch_Changed(self, sender, args):
        self._refresh_props()

    def ApplyProps_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridPropViews.SelectedItems or [])
        if not rows:
            forms.alert(u'Select at least one view in the list.')
            return
        scale = detail = disc = None
        if self.ChkPropScale.IsChecked:
            try:
                scale = int(self.TxtPropScale.Text.strip())
            except Exception:
                forms.alert(u'Enter a valid scale.')
                return
        if self.ChkPropDetail.IsChecked:
            detail = str(self.CmbPropDetail.SelectedItem or u'Medium')
        if self.ChkPropDisc.IsChecked:
            disc = str(self.CmbPropDisc.SelectedItem or u'Structural')
        if not any([scale, detail, disc]):
            forms.alert(u'Tick at least one property to set.')
            return
        ids = [r._rec['id'] for r in rows]
        self.SetLoading(True, u'Applying properties…')
        try:
            ok, failed, errors = _logic.set_view_properties(
                self.doc, ids, scale, detail, disc)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Properties applied: {}  ·  Failed: {}'.format(ok, failed)
        if errors:
            forms.alert(u'\n'.join(errors[:8]), title=u'View Manager — warnings')
        self._all_views = _vbm.collect_views(self.doc)
        self._refresh_props()

    # ── clean tab ─────────────────────────────────────────────────────────────

    def RefreshClean_Click(self, sender, args):
        self._refresh_clean()

    def DeleteViews_Click(self, sender, args):
        from pyrevit import forms
        rows = list(self.GridClean.SelectedItems or [])
        if not rows:
            forms.alert(u'Select the views to delete.')
            return
        if not forms.alert(
                u'Delete {} unplaced view(s)?\nThis can be undone with Revit undo.'.format(len(rows)),
                yes=True, no=True):
            return
        ids = [r._rec['id_obj'] for r in rows]
        self.SetLoading(True, u'Deleting views…')
        try:
            deleted, failed = _logic.delete_views(self.doc, ids)
        finally:
            self.SetLoading(False)
        self.TxtStatus.Text = u'Deleted: {}  ·  Failed: {}'.format(deleted, failed)
        self._refresh_clean()
        self._all_views = _vbm.collect_views(self.doc)
        self._refresh_dup()
        self._refresh_rename()
        self._refresh_tpl()
