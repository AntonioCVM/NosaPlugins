# -*- coding: utf-8 -*-
"""
ViewUtilities hub — consolidates AlignViewTitles, BaySections, LevelNavigator
and ViewDependencyExplorer into one sidebar-navigation window, plus two
Quick Action buttons (Halftone Selection, Section Boxer) that call straight
into their extracted logic without a tab of their own.

Follows the FootingDesigner / PileMaster pattern:
  - each absorbed tool's controls/handlers get a short unique prefix
    (AV_, BS_, LN_, VD_) in both XAML and Python.
  - each absorbed tool's logic.py is copied into this hub's lib/ under a
    globally-unique filename and loaded via imp.load_source() with a
    globally-unique module alias, to avoid the sys.modules collision that
    happens when two plugins in the same Revit session both ship a
    same-named 'logic.py'.
  - a single shared TxtStatus / LoadingPanel / ProcessBar trio (fixed names)
    is written by whichever tab is currently active, via the base class's
    SetLoading().
"""
import os
import sys
import System.Windows
from System.Collections.ObjectModel import ObservableCollection

from pyrevit import forms, revit
from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils import unit_conversion as _uc10

_here = os.path.dirname(os.path.abspath(__file__))
from nosa_utils.bootstrap import load_module
_align_logic    = load_module('vu_align_logic',    os.path.join(_here, 'logic_align_view_titles.py'))
_bay_logic      = load_module('vu_bay_logic',       os.path.join(_here, 'logic_bay_sections.py'))
_level_logic    = load_module('vu_level_logic',     os.path.join(_here, 'logic_level_navigator.py'))
_viewdep_logic  = load_module('vu_viewdep_logic',   os.path.join(_here, 'logic_view_dependency_explorer.py'))
_halftone_logic = load_module('vu_halftone_logic',  os.path.join(_here, 'logic_halftone_selection.py'))
_secbox_logic   = load_module('vu_secbox_logic',    os.path.join(_here, 'logic_section_boxer.py'))


# ══════════════════════════════════════════════════════════════════════════
# Row / item wrapper classes (ported unchanged from each original tool's ui.py)
# ══════════════════════════════════════════════════════════════════════════

class _ViewportItem(object):
    def __init__(self, data):
        self.SheetNumber = data['sheet_num']
        self.ViewName = data['view_name']
        self.Viewport = data['viewport']
        self.View = data['view']
        self.Data = data


class _SheetSetItem(object):
    def __init__(self, name):
        self.Name = name
        self.IsChecked = False

    def __repr__(self):
        return self.Name


class _GridRow(object):
    def __init__(self, grid_dict):
        self.SelA     = False
        self.SelB     = False
        self._grid_id = grid_dict['id']
        self.Name     = grid_dict['name']
        self.GridType = u'Arc' if grid_dict['is_arc'] else u'Linear'


class _LevelRow(object):
    def __init__(self, d):
        self.Name       = d['name']
        self.Elevation  = u'{:.3f} m'.format(d['elevation_m'])
        self.ViewName   = d['view_name'] or u'— no view —'
        self.Discipline = d['view_disc']
        self.HasView    = d['view_id'] is not None
        self.StatusIcon = u'✓' if self.HasView else u'–'
        self._view_id   = d['view_id']


class _DepRow(object):
    def __init__(self, dep_type, name, detail):
        self.DepType = dep_type
        self.Name    = name
        self.Detail  = detail


# ══════════════════════════════════════════════════════════════════════════
# Hub window
# ══════════════════════════════════════════════════════════════════════════

class ViewUtilitiesWindow(NOSAWindow):

    def __init__(self, doc, uidoc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'view_utilities')
        # SelectionChanged/SelectedIndex wired in code after LoadComponent, never in XAML (NOSA106)
        self.AV_ComboMode.SelectedIndex = 0
        self.LN_GridLevels.SelectionChanged += self.LN_Grid_SelectionChanged
        self.doc   = doc
        self.uidoc = uidoc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        # ---- AV: Align View Titles ----
        self.av_logic          = _align_logic.AlignLogic(doc)
        self.av_ref_vp         = None
        self.av_ref_view       = None
        self.av_ref_offset     = None
        self.av_matching_items = []
        self.av_preview_items  = ObservableCollection[object]()
        self.AV_GridPreview.ItemsSource = self.av_preview_items
        self.av_sheet_sets = ObservableCollection[object]()
        self.AV_ListSheetSets.ItemsSource = self.av_sheet_sets
        self._av_load_sheet_sets()

        # ---- BS: Bay Sections ----
        self._bs_grid_rows = ObservableCollection[object]()
        self.BS_GridList.ItemsSource = self._bs_grid_rows
        self.BS_TxtPrefix.Text = cfg.get('bs_prefix', u'S')
        self.BS_TxtDepthOffset.Text = str(cfg.get('bs_depth_offset', 3000))
        self._bs_populate_view_types()
        self._bs_populate_grids()

        # ---- LN: Level Navigator ----
        self._ln_rows = ObservableCollection[object]()
        self.LN_GridLevels.ItemsSource = self._ln_rows
        self._ln_load()

        # ---- VD: View Dependency Explorer ----
        self._vd_views = []
        self._vd_rows  = ObservableCollection[object]()
        self.VD_DepGrid.ItemsSource = self._vd_rows
        self._vd_load_views()

        # ---- Sidebar nav ----
        self._nav_tabs = {
            'BtnTabAlign':   self.PanelAlign,
            'BtnTabBay':     self.PanelBay,
            'BtnTabLevel':   self.PanelLevel,
            'BtnTabViewDep': self.PanelViewDep,
        }

    # ══════════════════════════════════════════════════════════════════
    # Sidebar navigation
    # ══════════════════════════════════════════════════════════════════

    def NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._nav_tabs)

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: ALIGN VIEW TITLES  (prefix AV_)
    # ══════════════════════════════════════════════════════════════════

    def _av_load_sheet_sets(self):
        for s in self.av_logic.get_sheet_sets():
            self.av_sheet_sets.Add(_SheetSetItem(s))

    def AV_Filter_Toggled(self, sender, args):
        vis = System.Windows.Visibility.Visible if self.AV_ChkFilterSheets.IsChecked else System.Windows.Visibility.Collapsed
        self.AV_ListSheetSets.Visibility = vis

    def AV_PickRef_Click(self, sender, args):
        self.Hide()
        try:
            ref_pick = self.uidoc.Selection.PickObject(ObjectType.Element, "Select reference viewport")
            elem = self.doc.GetElement(ref_pick.ElementId)

            if isinstance(elem, DB.Viewport):
                self.av_ref_vp = elem
                self.av_ref_view = self.doc.GetElement(elem.ViewId)
                try:
                    self.av_ref_offset = self.av_ref_vp.LabelOffset
                except Exception as ex:
                    forms.alert(
                        u"Cannot read LabelOffset from this viewport.\n"
                        u"The viewport type may have 'Show Title' disabled.\n\n"
                        u"Detail: {}".format(ex))
                    self.av_ref_vp = None
                    self.av_ref_view = None
                    return

                ox = round(self.av_ref_offset.X * 304.8, 1)
                oy = round(self.av_ref_offset.Y * 304.8, 1)
                offset_note = u"  Offset: ({} mm, {} mm)".format(ox, oy)
                if ox == 0.0 and oy == 0.0:
                    offset_note += u"  ⚠ default — drag the title first!"

                self.AV_TxtRefView.Text = self.av_ref_view.Name
                self.AV_TxtRefScale.Text = u"Scale 1:{}{}".format(
                    self.av_ref_view.Scale, offset_note)
                self.AV_PanelRefInfo.Visibility = System.Windows.Visibility.Visible
            else:
                forms.alert("Not a viewport.")
        except OperationCanceledException:
            pass
        except Exception as e:
            forms.alert("Could not pick reference viewport: {}".format(str(e)))
        finally:
            self.Show()

    def AV_Preview_Click(self, sender, args):
        if not self.av_ref_vp:
            forms.alert("Please pick a reference viewport first.")
            return

        filter_sets = None
        if self.AV_ChkFilterSheets.IsChecked:
            selected = [item.Name for item in self.AV_ListSheetSets.SelectedItems]
            if selected:
                filter_sets = selected

        self.av_matching_items, debug_report = self.av_logic.get_matching_viewports(
            self.av_ref_view,
            filter_sets
        )

        self.av_preview_items.Clear()
        for m in self.av_matching_items:
            self.av_preview_items.Add(_ViewportItem(m))

        self.AV_TxtCount.Text = "{} found".format(len(self.av_matching_items))

        if not self.av_matching_items:
            forms.alert(
                "No matching viewports found.\n(Matches must have SAME Scale and Compatible View Type)\n\n" + debug_report,
                title="Search Diagnosis",
                warn_icon=True
            )

    def AV_Apply_Click(self, sender, args):
        if not self.av_matching_items:
            forms.alert("Run preview first.")
            return

        mode = self.AV_ComboMode.Text
        vertical = bool(self.AV_ChkVertical.IsChecked)

        count = 0
        errors = []
        with revit.Transaction("Align Titles"):
            for item in self.av_matching_items:
                try:
                    target_vp = item['viewport']
                    new_offset = self.av_logic.calculate_aligned_offset(
                        self.av_ref_offset,
                        self.av_ref_vp,
                        target_vp,
                        mode,
                        vertical
                    )
                    target_vp.LabelOffset = new_offset
                    count += 1
                except Exception as ex:
                    err_msg = u'{}: {}'.format(item.get('view_name', '?'), ex)
                    errors.append(err_msg)

        msg = u'Aligned: {}'.format(count)
        if errors:
            msg += u'\nFailed: {}\n\nFirst error:\n{}'.format(
                len(errors), errors[0])
        forms.alert(msg)
        if count > 0:
            self.Close()

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: BAY SECTIONS  (prefix BS_)
    # ══════════════════════════════════════════════════════════════════

    def _bs_log(self, msg):
        """Mirrors NOSAWindow.LogLine() but targets BS_TxtLog (this tab's
        own prefixed log box) instead of the fixed 'TxtLog' name the base
        class looks for."""
        try:
            self.BS_TxtLog.AppendText(msg + "\n")
            self.BS_TxtLog.ScrollToEnd()
        except Exception:
            pass

    def _bs_populate_view_types(self):
        self.BS_CmbViewType.Items.Clear()
        self._bs_view_types = _bay_logic.get_view_family_types(self.doc)
        for vt in self._bs_view_types:
            self.BS_CmbViewType.Items.Add(_bay_logic.safe_element_name(vt))
        if self._bs_view_types:
            self.BS_CmbViewType.SelectedIndex = 0

    def _bs_populate_grids(self):
        self._bs_grid_rows.Clear()
        for g in _bay_logic.get_grids(self.doc):
            self._bs_grid_rows.Add(_GridRow(g))
        self.BS_GridList.ItemsSource = self._bs_grid_rows
        self._bs_log(u'Loaded {} grids.'.format(self._bs_grid_rows.Count))

    def BS_Generate_Click(self, sender, args):
        grids_a = [r for r in self._bs_grid_rows if r.SelA]
        grids_b = [r for r in self._bs_grid_rows if r.SelB]

        if not grids_a or not grids_b:
            self._bs_log(u'Select at least one grid as A and one as B.')
            return

        vt_idx = self.BS_CmbViewType.SelectedIndex
        if vt_idx < 0 or vt_idx >= len(self._bs_view_types):
            self._bs_log(u'Select a section view type.')
            return
        vt_id = self._bs_view_types[vt_idx].Id

        try:
            depth_mm = float(self.BS_TxtDepthOffset.Text or u'3000')
        except Exception:
            depth_mm = 3000.0
        depth_ft = depth_mm * _uc10.MM_TO_FT

        prefix = self.BS_TxtPrefix.Text or u'S'

        self.SetLoading(True, u'Generating sections...')
        created = 0
        errors  = 0
        # Computed once — the model's own extents don't depend on which
        # grid pair is being sectioned, so scanning the whole document
        # again inside the grids_a x grids_b loop below would repeat the
        # same document-wide scan once per pair for an identical result.
        model_extents = _bay_logic._get_model_extents(self.doc)
        try:
            with DB.Transaction(self.doc, u'NOSA — Bay Sections') as t:
                t.Start()
                for row_a in grids_a:
                    for row_b in grids_b:
                        if row_a._grid_id == row_b._grid_id:
                            continue
                        views = _bay_logic.create_bay_sections(
                            self.doc,
                            row_a._grid_id, row_b._grid_id,
                            vt_id, depth_ft, depth_ft / 2.0, prefix,
                            model_extents=model_extents)
                        created += len(views)
                t.Commit()
        except Exception as e:
            self._bs_log(u'Error: {}'.format(e))
            errors += 1
        finally:
            self.SetLoading(False)

        self._bs_log(u'Created {} section view(s). {} error(s).'.format(created, errors))

        cfg = self.LoadConfig()
        cfg.update({'bs_prefix': prefix, 'bs_depth_offset': depth_mm, 'dark_mode': self.dark_mode})
        self.SaveConfig(cfg)

    def BS_SelectAllA_Click(self, sender, args):
        for row in self._bs_grid_rows:
            row.SelA = True
        self.BS_GridList.Items.Refresh()

    def BS_Close_Click(self, sender, args):
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # TAB 3: LEVEL NAVIGATOR  (prefix LN_)
    # ══════════════════════════════════════════════════════════════════

    def _ln_load(self):
        self._ln_rows.Clear()
        data = _level_logic.get_levels_with_views(self.doc)
        for d in data:
            self._ln_rows.Add(_LevelRow(d))
        total    = len(data)
        no_view  = sum(1 for d in data if d['view_id'] is None)
        self.LN_TxtTotal.Text   = u'{} levels'.format(total)
        self.LN_TxtNoView.Text  = u'{} without view'.format(no_view)
        self.LN_BtnActivate.IsEnabled = False

    def LN_Refresh_Click(self, sender, args):
        self._ln_load()

    def LN_Grid_SelectionChanged(self, sender, args):
        row = self.LN_GridLevels.SelectedItem
        self.LN_BtnActivate.IsEnabled = (row is not None and row.HasView)

    def LN_Grid_MouseDoubleClick(self, sender, args):
        self._ln_activate_selected()

    def LN_Activate_Click(self, sender, args):
        self._ln_activate_selected()

    def _ln_activate_selected(self):
        row = self.LN_GridLevels.SelectedItem
        if row is None or not row.HasView:
            return
        try:
            _level_logic.activate_view(self.uidoc, row._view_id)
            cfg = self.LoadConfig()
            cfg['dark_mode'] = self.dark_mode
            self.SaveConfig(cfg)
            self.Close()
        except Exception as e:
            forms.alert(u'Could not activate view: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 4: VIEW DEPENDENCY EXPLORER  (prefix VD_)
    # ══════════════════════════════════════════════════════════════════

    def _vd_load_views(self):
        self.VD_ViewList.Items.Clear()
        self._vd_views = _viewdep_logic.get_all_views(self.doc)
        for vi in self._vd_views:
            self.VD_ViewList.Items.Add(
                u'[{}]  {}'.format(vi['type'], vi['name']))
        self.VD_TxtResult.Text = u'{} views available.'.format(len(self._vd_views))

    def VD_Analyse_Click(self, sender, args):
        idx = self.VD_ViewList.SelectedIndex
        if idx < 0 or idx >= len(self._vd_views):
            forms.alert(u'Select a view first.', title=u'View Dependency Explorer')
            return
        vi = self._vd_views[idx]
        self.SetLoading(True, u'Analysing dependencies…')
        try:
            data = _viewdep_logic.analyse_view(self.doc, vi['id'])
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'View Dependency Explorer')
            return

        self._vd_rows.Clear()

        # Template
        if data['template']:
            self._vd_rows.Add(_DepRow(u'Template', data['template']['name'],
                                      u'ID {}'.format(data['template']['id'])))
        else:
            self._vd_rows.Add(_DepRow(u'Template', u'(none — no template applied)', u''))

        # Filters
        for f in data['filters']:
            vis = u'Visible' if f['visible'] else u'Hidden'
            self._vd_rows.Add(_DepRow(u'Filter', f['name'], vis))
        if not data['filters']:
            self._vd_rows.Add(_DepRow(u'Filter', u'(no filters applied)', u''))

        # Sheets
        for sh in data['sheets']:
            self._vd_rows.Add(_DepRow(u'Sheet', u'{} — {}'.format(sh['number'], sh['name']), u''))
        if not data['sheets']:
            self._vd_rows.Add(_DepRow(u'Sheet', u'(not placed on any sheet)', u''))

        # Revisions
        for rv in data['revisions']:
            detail = u'{} · {}'.format(rv['date'], rv['sheet']) if rv['date'] else rv['sheet']
            self._vd_rows.Add(_DepRow(u'Revision', rv['description'] or rv['sequence'], detail))
        if not data['revisions']:
            self._vd_rows.Add(_DepRow(u'Revision', u'(no revisions found on hosting sheets)', u''))

        # Dependent views
        for dv in data['dependent_views']:
            self._vd_rows.Add(_DepRow(u'Dependent', dv['name'], u'ID {}'.format(dv['id'])))
        if not data['dependent_views']:
            self._vd_rows.Add(_DepRow(u'Dependent', u'(no dependent views)', u''))

        self.SetLoading(False)

        n_tmpl  = 1 if data['template'] else 0
        n_filt  = len(data['filters'])
        n_sheet = len(data['sheets'])
        n_rev   = len(data['revisions'])
        n_dep   = len(data['dependent_views'])
        self.VD_TxtResult.Text = (
            u'{} — {} template · {} filter(s) · {} sheet(s) · '
            u'{} revision(s) · {} dependent view(s)'.format(
                vi['name'], n_tmpl, n_filt, n_sheet, n_rev, n_dep))

    def VD_Close_Click(self, sender, args):
        # Original ViewDependencyExplorer overwrote its (dedicated) config
        # file with just {'dark_mode': ...} on close. In the hub the config
        # file is shared across all 4 tabs, so we merge instead of
        # overwriting — same end effect (dark mode is saved before close)
        # without discarding BS_'s prefix/depth-offset settings.
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
        self.Close()

    # ══════════════════════════════════════════════════════════════════
    # QUICK ACTIONS — Halftone Selection / Section Boxer
    # ══════════════════════════════════════════════════════════════════

    def QuickHalftone_Click(self, sender, args):
        _halftone_logic.apply_halftone(self.doc, self.uidoc)

    def QuickSectionBox_Click(self, sender, args):
        _secbox_logic.create_section_box(self.doc, self.uidoc)

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
