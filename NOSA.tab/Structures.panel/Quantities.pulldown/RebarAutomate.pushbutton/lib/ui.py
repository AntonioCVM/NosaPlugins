# -*- coding: utf-8 -*-
import os, sys

from pyrevit import forms, revit
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Windows.Media import SolidColorBrush, Color
from System.Collections.Generic import List

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value
from nosa_utils.bootstrap import load_module
from nosa_utils import shared_params
from nosa_utils import standards

_HERE = os.path.dirname(__file__)
# PHASE F0 — migrated from imp.load_source to nosa_utils.bootstrap's
# unified loader (tries importlib first, falls back to imp — a strict
# superset of the old behaviour). Registered module names are UNCHANGED
# (re_engine, footing_rebar, rebar_detailing, column_rebar, beam_rebar,
# floor_rebar, rebar_preview) — several sibling modules cross-reference
# each other by exactly these names via sys.modules, so renaming any of
# them here would break those references.
re_engine = load_module('re_engine', os.path.join(_HERE, 'rebar_engine.py'))
footing_rebar = load_module('footing_rebar', os.path.join(_HERE, 'footing_rebar.py'))
rebar_detailing = load_module('rebar_detailing', os.path.join(_HERE, 'rebar_detailing.py'))
# Phase 1 dashboard scaffold — the next three are loaded here (isolated,
# same bootstrap.load_module convention as the rest of this plugin) so
# the module-wiring itself is proven end-to-end before their own phases
# (2/3/4) add real logic. floor_rebar/rebar_preview are new Phase 1
# scaffolds (NotImplementedError placeholders); column_rebar/beam_rebar
# already existed from this plugin's very first geometry sprint but were
# never wired into ui.py or the Set/global-bbox/Z-layering architecture
# footings ended up with — that reconciliation is Phase 3/4's job, not
# this one's.
column_rebar = load_module('column_rebar', os.path.join(_HERE, 'column_rebar.py'))
beam_rebar = load_module('beam_rebar', os.path.join(_HERE, 'beam_rebar.py'))
floor_rebar = load_module('floor_rebar', os.path.join(_HERE, 'floor_rebar.py'))
wall_rebar = load_module('wall_rebar', os.path.join(_HERE, 'wall_rebar.py'))
rebar_preview = load_module('rebar_preview', os.path.join(_HERE, 'rebar_preview.py'))
# PHASE F1
rebar_batch = load_module('rebar_batch', os.path.join(_HERE, 'rebar_batch.py'))
rebar_project = load_module('rebar_project', os.path.join(_HERE, 'rebar_project.py'))
_version_mod = load_module('rebarautomate_version', os.path.join(_HERE, '_version.py'))
# PHASE F5/F8 — rebar_schedule was previously loaded ad-hoc with a raw
# imp.load_source(...) inside BtnGenerateSchedule_Click's own body
# (mislabelled in a comment there as "load_module ... IronPython
# compatible"), every time the button was clicked, unlike every other
# sibling module above. Moved here to match the established convention —
# load once, at import time, via the real bootstrap.load_module facade.
rebar_schedule = load_module('rebar_schedule', os.path.join(_HERE, 'rebar_schedule.py'))
rebar_export_bvbs = load_module('rebar_export_bvbs', os.path.join(_HERE, 'rebar_export_bvbs.py'))

_CAT_ID_CACHE = {}


def _cat_id(bic_name):
    """Integer id of a BuiltInCategory, resolved on first use (never at import time)."""
    if bic_name not in _CAT_ID_CACHE:
        bic = getattr(DB.BuiltInCategory, bic_name)
        _CAT_ID_CACHE[bic_name] = get_id_value(DB.ElementId(bic))
    return _CAT_ID_CACHE[bic_name]

_PREVIEW_BAR_FILL = SolidColorBrush(Color.FromRgb(51, 51, 51))
_PREVIEW_SECTION_STROKE = SolidColorBrush(Color.FromRgb(255, 95, 0))
_PREVIEW_SECTION_FILL = SolidColorBrush(Color.FromArgb(15, 255, 95, 0))
# Phase 2.1 — Perimeter Closure U-Bars preview: 'primary' (X-Bars
# Anchoring, B1/T1) drawn solid, matching the main mat's own bar
# colour; 'weave' (Y-Bars Anchoring, B2/T2) drawn semi-transparent in
# the accent colour — the "distinctive secondary visual" the brief
# asked for to conceptualise the two directions crossing at the
# corners without clashing (they sit at different Z, exactly like the
# main mat's own B1/B2 and T1/T2 layers already do).
_PREVIEW_UBAR_PRIMARY_STROKE = SolidColorBrush(Color.FromRgb(51, 51, 51))
_PREVIEW_UBAR_WEAVE_STROKE = SolidColorBrush(Color.FromArgb(140, 255, 95, 0))

# Phase 5.4: mat bars no longer use RebarHookType at all — they get
# explicit full-depth U-bar legs instead (see footing_rebar.py's module
# docstring). RebarHookType is now used ONLY for dowels.
# RebarHookOrientation.Left picks one of the two directions within the
# vertical hook plane (up vs down) for that dowel hook; if it comes out
# upside down, flip this to Right (see rebar_engine.py's API confidence
# notes — this specific choice is still an unverified guess for dowels).
_HOOK_ORIENTATION = DBS.RebarHookOrientation.Left


class _CategorySelectionFilter(ISelectionFilter):
    """Restricts PickObjects to one or more OST_* category ids."""

    def __init__(self, category_ids):
        self._category_ids = set(category_ids)

    def AllowElement(self, element):
        return (element.Category is not None and
                get_id_value(element.Category.Id) in self._category_ids)

    def AllowReference(self, ref, point):
        return True


class _ReinforcementEventHandler(IExternalEventHandler):
    """
    PHASE 3.5.7 item 4 — parametrized IExternalEventHandler for the
    Configure -> Generate -> Select -> Apply flow. RebarAutomate has no
    separate pre-selection button (unlike the sibling AddPileToPilecap
    plugin), so BOTH the Revit-API PickObjects call and the
    reinforcement Transaction must run inside this single Execute()
    callback, triggered from one "Generate" click.
    """

    def __init__(self, window):
        self.window = window
        self.pending = None

    def Execute(self, uiapp):
        window = self.window
        ctx = self.pending
        self.pending = None
        if ctx is None:
            window.Show()
            return
        uidoc = uiapp.ActiveUIDocument
        mode = ctx['mode']
        values = ctx['values']
        try:
            if mode == 'columns':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_StructuralColumns')])
                prompt = u'Select Structural Columns to reinforce, then click Finish.'
            elif mode == 'beams':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_StructuralFraming')])
                prompt = u'Select Structural Framing (beams) to reinforce, then click Finish.'
            elif mode == 'walls':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_Walls')])
                prompt = u'Select Walls to reinforce, then click Finish.'
            else:
                sel_filter = _CategorySelectionFilter([_cat_id('OST_StructuralFoundation'), _cat_id('OST_Floors')])
                prompt = (u'Select Structural Foundations and/or Floors to reinforce, '
                          u'then click Finish.')

            try:
                refs = uidoc.Selection.PickObjects(ObjectType.Element, sel_filter, prompt)
            except OperationCanceledException:
                # Silent cancel — user backed out of selection. Focus
                # returns to the window via the outer finally below.
                return

            elements = [uidoc.Document.GetElement(r.ElementId) for r in refs]
            if elements and not window._ensure_shared_params():
                return

            if mode == 'columns':
                if not elements:
                    forms.alert(u'No Structural Columns selected.')
                    return
                window.SetLoading(True, u'Generating column reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'),
                        layers=window._pending_layers)
                    batch_result = batch.run(
                        lambda: window._run_column_reinforcement(elements, values))
                    summary = dict(batch_result.summary)
                    summary['errors'] = batch_result.errors
                except Exception as e:
                    forms.alert(u'Column reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_column_result(elements, summary)
                window._refresh_batch_list()
            elif mode == 'beams':
                if not elements:
                    forms.alert(u'No Structural Framing (beams) selected.')
                    return
                window.SetLoading(True, u'Generating beam reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'),
                        layers=window._pending_layers)
                    batch_result = batch.run(
                        lambda: window._run_beam_reinforcement(elements, values))
                    summary = dict(batch_result.summary)
                    summary['errors'] = batch_result.errors
                except Exception as e:
                    forms.alert(u'Beam reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_beam_result(elements, summary)
                window._refresh_batch_list()
            elif mode == 'walls':
                if not elements:
                    forms.alert(u'No Walls selected.')
                    return
                window.SetLoading(True, u'Generating wall reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'),
                        layers=window._pending_layers)
                    batch_result = batch.run(
                        lambda: window._run_wall_reinforcement(elements, values))
                    summary = dict(batch_result.summary)
                    summary['errors'] = batch_result.errors
                except Exception as e:
                    forms.alert(u'Wall reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_wall_result(elements, summary)
                window._refresh_batch_list()
            else:
                footings = [e for e in elements if e.Category is not None and
                            get_id_value(e.Category.Id) == _cat_id('OST_StructuralFoundation')]
                floors = [e for e in elements if e.Category is not None and
                          get_id_value(e.Category.Id) == _cat_id('OST_Floors')]
                if not footings and not floors:
                    forms.alert(u'No Structural Foundations or Floors selected.')
                    return

                footings_only_extras = (values['include_side_rebar'] or values['include_dowels']
                                        or values['generate_sections'])
                if footings_only_extras and floors and not footings:
                    forms.alert(u'Side Rebar, Dowels and Detail Sections are footing-only '
                                u'features. Only Floors are selected, so they will be '
                                u'skipped for this run.')

                window.SetLoading(True, u'Generating reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'),
                        layers=window._pending_layers)
                    batch_result = batch.run(
                        lambda: window._run_reinforcement(footings, floors, values))
                    summary = dict(batch_result.summary)
                    summary['errors'] = batch_result.errors
                except Exception as e:
                    forms.alert(u'Reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_reinforcement_result(footings, floors, summary)
                window._refresh_batch_list()
        finally:
            window.Show()

    def GetName(self):
        return u'NOSA RebarAutomate — Reinforcement Generation'


class RebarAutomateWindow(NOSAWindow):

    def __init__(self, doc):
        # PHASE 3.6 FIX — a live crash ("Initialization of
        # 'System.Windows.Controls.ComboBox' threw an exception")
        # traced to XAML-declared SelectedIndex/SelectionChanged on a
        # ComboBox/TabControl: IronPython's wpf.LoadComponent parses
        # the XAML top-to-bottom and instantiates each element as it
        # goes: setting SelectedIndex="0" directly in XAML fires
        # SelectionChanged IMMEDIATELY, during that same parse pass —
        # before every named control on `self` exists yet, and before
        # this object is a fully-constructed Python instance. A
        # handler that touches ANY other x:Name control (as
        # ColumnPreview_Changed does) crashes right there. Fixed by:
        # (1) removing every SelectedIndex/SelectedItem/
        # SelectionChanged attribute from the XAML itself (ui.xaml now
        # declares ComboBox/TabControl structure only), (2) setting
        # defaults and wiring events here in code, STRICTLY AFTER
        # NOSAWindow.__init__ (i.e. after wpf.LoadComponent) has
        # returned and every control genuinely exists, and (3) an
        # explicit self._is_loaded flag every event handler in this
        # class checks first, so even an unanticipated early event
        # (e.g. from a future control) can't reach code that assumes
        # __init__ has finished.
        self._is_loaded = False

        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'rebar_automate')
        self.doc = doc
        self.uidoc = revit.uidoc

        # PHASE 3.5.7 item 4 — anchored on self so .NET's GC doesn't
        # collect the handler/event while the window (and any pending
        # Raise()) is still alive.
        self._reinforcement_handler = _ReinforcementEventHandler(self)
        self._reinforcement_event = ExternalEvent.Create(self._reinforcement_handler)

        # Shared parameters are bound lazily by _ensure_shared_params(),
        # right before the first generation writes NOSA data: opening the
        # window never modifies the model.
        self.ra_project = rebar_project.load(self.doc)
        self.ra_generator_version = _version_mod.RA_VERSION
        self._shared_params_report = None
        self._pending_layers = {}

        # PHASE F2 — normativa (rebar standard) profile, resolved once at
        # launch and re-resolved whenever the user changes the "Standard:"
        # dropdown. self.ra_standard is the full profile dict consumed by
        # standards.cover_for/lap_length_mm/etc; self.ra_project holds the
        # persisted code string (rebar_project.json's 'standard_code').
        self.ra_standard = self._load_standard(self.ra_project.get('standard_code', u'EHE-08'))
        self._populate_standard_dropdown()
        self._populate_project_header()
        self._populate_detailing_combos()

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        # Defaults + event wiring for every ComboBox, done in code —
        # see the Phase 3.6 note above for why this can never be a
        # XAML attribute on the ComboBox itself.
        self.CmbDowelCount.SelectedIndex = 0
        self.CboCrosstieLayout.SelectedIndex = 0
        self.CboCrosstieLayout.SelectionChanged += self.ColumnPreview_Changed
        self.MainTabControl.SelectionChanged += self.MainTabControl_SelectionChanged
        self.CmbStandard.SelectionChanged += self.CmbStandard_SelectionChanged

        self._update_preview()
        self._update_column_preview()
        self._update_beam_preview()
        self._update_wall_preview()
        # PHASE 3.5 item 3 — re-read the CURRENT Revit selection once
        # the window is fully shown (Canvas layout/measurement hasn't
        # necessarily settled at construction time) and again every
        # time the user switches TO the Columns tab (e.g. they select
        # a different column in the model AFTER opening this window,
        # then flip back to check the preview) — _update_column_preview
        # itself is the one that reads self._selected_columns() /
        # column_rebar.detect_column_geometry, so re-calling it is
        # enough; no separate "diff the selection" tracking needed.
        self.Loaded += self._on_window_loaded

        self._is_loaded = True
        self._refresh_batch_list()

    def _on_window_loaded(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_column_preview()

    def MainTabControl_SelectionChanged(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        # SelectionChanged is a routed/bubbling event — a ComboBox
        # INSIDE a tab's own content (e.g. CboCrosstieLayout) also
        # raises it, and it bubbles up to this TabControl. Only react
        # when the TabControl itself is the actual source of the
        # change (a genuine tab switch), not a bubbled selection
        # change from a nested control.
        #
        # PHASE 3.5.1 item 4 fix — this used to check
        # args.OriginalSource, which for a routed SelectionChanged is
        # the deepest visual element the event actually occurred on
        # (a TabItem's internal chrome/border on a real tab click) —
        # almost NEVER the TabControl itself, so this guard discarded
        # nearly every genuine tab switch and the preview never
        # refreshed ("frozen" live). args.Source is the Selector that
        # actually raised the change (the TabControl for a tab switch,
        # the ComboBox for a combo change) — the correct check here.
        if args.Source is not self.MainTabControl:
            return
        self._update_column_preview()
        self._update_beam_preview()
        self._update_wall_preview()

    # ── normativa (rebar standard) — PHASE F2 ───────────────────────────

    def _ensure_shared_params(self):
        """Bind NOSA's shared parameters once per window; False if binding failed outright."""
        if self._shared_params_report is not None:
            return not self._shared_params_report.get('fatal', False)
        print(u'\n' + u'=' * 80)
        print(u'NOSA RebarAutomate — Verifying shared parameters...')
        try:
            report = shared_params.ensure_bound(self.doc)
        except Exception as e:
            self._shared_params_report = {'bound': [], 'already': [], 'skipped': [],
                                          'errors': [u'ensure_bound failed: {}'.format(e)],
                                          'fatal': True}
            print(u'\n✗ CRITICAL ERROR creating shared parameters: {}\n'.format(e))
            forms.alert(
                u'CRITICAL ERROR: Could not create shared parameters.\n\n'
                u'Error: {}\n\n'
                u'Check the pyRevit console (Ctrl+F8) for details.\n\n'
                u'NOSA features will not work until this is resolved.'.format(e),
                title=u'NOSA RebarAutomate — Error',
                warn_icon=True)
            return False
        self._shared_params_report = report

        errors = report.get('errors', [])
        print(u'  ✓ Newly bound: {} parameters'.format(len(report.get('bound', []))))
        print(u'  ✓ Already bound: {} parameters'.format(len(report.get('already', []))))
        if report.get('skipped'):
            print(u'  ⚠ Skipped: {} parameters'.format(len(report['skipped'])))
        if errors:
            print(u'  ✗ Errors: {} parameters'.format(len(errors)))
            for err in errors:
                print(u'    - {}'.format(err))
        print(u'=' * 80 + u'\n')

        if errors:
            forms.alert(
                u'WARNING: {} error(s) occurred while creating shared parameters.\n\n'
                u'Check the pyRevit console (Ctrl+F8) for details.\n\n'
                u'Some NOSA features may not work correctly.'.format(len(errors)),
                title=u'NOSA RebarAutomate — Shared Parameters',
                warn_icon=True)
        return True

    def _load_standard(self, code):
        """Resolve a rebar-standard profile dict for `code`, falling back
        to EHE-08 and finally to None (never raises) so a missing/corrupt
        user-override file under NOSA_Configs/rebar_standards/ can never
        crash the window. Every call site that consumes the result treats
        None the same as "no standard resolved" — the pre-F2 hardcoded
        defaults (DEFAULT_COVER_MM etc.) apply, matching this plugin's
        behaviour before this phase existed."""
        try:
            return standards.load(code)
        except Exception:
            if code != u'EHE-08':
                try:
                    return standards.load(u'EHE-08')
                except Exception:
                    pass
            return None

    def _populate_standard_dropdown(self):
        """Global "Standard:" selector (ui.xaml, outside the TabControl).
        Populated here in code from standards.list_available() — never
        XAML SelectedIndex/SelectionChanged, per the Phase 3.6 note above
        in __init__. Called BEFORE CmbStandard.SelectionChanged is wired,
        so setting SelectedItem here does not fire the handler."""
        codes = standards.list_available()
        if not codes:
            codes = [u'EHE-08']
        self.CmbStandard.Items.Clear()
        for code in codes:
            self.CmbStandard.Items.Add(code)
        current_code = self.ra_project.get('standard_code', u'EHE-08')
        if current_code not in codes:
            current_code = codes[0]
        self.CmbStandard.SelectedItem = current_code

    def CmbStandard_SelectionChanged(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        code = self.CmbStandard.SelectedItem
        if not code:
            return
        self.ra_standard = self._load_standard(code)
        self.ra_project['standard_code'] = code
        rebar_project.save(self.doc, self.ra_project)
        self._update_preview()
        self._update_column_preview()

    # ── project marking header — PHASE F3 ───────────────────────────────

    def _populate_project_header(self):
        """Cabecera de proyecto (F3): prefijo de marca, revisión, estado.
        Poblado en código desde rebar_project.json, nunca XAML SelectedIndex."""
        statuses = [u'Design', u'Construction', u'As-Built']
        self.CmbProjectStatus.Items.Clear()
        for status in statuses:
            self.CmbProjectStatus.Items.Add(status)
        
        # Cargar valores desde rebar_project.json
        self.TxtMarkPrefix.Text = self.ra_project.get('mark_prefix', u'')
        self.TxtRevision.Text = self.ra_project.get('revision', u'')
        current_status = self.ra_project.get('status', u'Design')
        if current_status in statuses:
            self.CmbProjectStatus.SelectedItem = current_status
        else:
            self.CmbProjectStatus.SelectedIndex = 0
        
        # Cablear botón Save (no usar SelectedIndex/SelectionChanged en XAML)
        self.BtnSaveProjectHeader.Click += self.BtnSaveProjectHeader_Click
        
        # Cablear botón Generate Schedule (F5)
        self.BtnGenerateSchedule.Click += self.BtnGenerateSchedule_Click
        self.BtnExportBvbs.Click += self.BtnExportBvbs_Click

    def BtnSaveProjectHeader_Click(self, sender, args):
        """Guarda prefijo de marca, revisión y estado en rebar_project.json."""
        if not getattr(self, '_is_loaded', False):
            return
        self.ra_project['mark_prefix'] = (self.TxtMarkPrefix.Text or u'').strip()
        self.ra_project['revision'] = (self.TxtRevision.Text or u'').strip()
        self.ra_project['status'] = self.CmbProjectStatus.SelectedItem or u'Design'
        rebar_project.save(self.doc, self.ra_project)
        forms.alert(u'Project settings saved.', title=u'RebarAutomate')
    
    def BtnGenerateSchedule_Click(self, sender, args):
        """Genera y exporta Bar Bending Schedule (BBS)."""
        if not getattr(self, '_is_loaded', False):
            return
        
        try:
            # rebar_schedule is loaded once at module level (top of this
            # file), matching every other sibling module's convention —
            # no per-click reload needed.

            # Generar schedule de todas las barras NOSA
            schedule_data = rebar_schedule.generate_schedule_data(
                self.doc, batch_id=None, include_finalized=False
            )
            
            if not schedule_data:
                forms.alert(u'No NOSA rebars found in the project.', 
                           title=u'Bar Bending Schedule')
                return
            
            # Calcular estadísticas
            stats = rebar_schedule.get_summary_stats(schedule_data)
            
            # Mostrar resumen
            summary_msg = u'Bar Bending Schedule Summary:\n\n'
            summary_msg += u'Total positions: {}\n'.format(stats['total_positions'])
            summary_msg += u'Total bars: {}\n'.format(stats['total_bars'])
            summary_msg += u'Total length: {:.2f} m\n'.format(stats['total_length_m'])
            summary_msg += u'Total weight: {:.1f} kg\n\n'.format(stats.get('total_weight_kg', 0.0))
            summary_msg += u'By diameter:\n'
            for dia in sorted(stats['by_diameter'].keys()):
                dia_stats = stats['by_diameter'][dia]
                summary_msg += u'  Ø{} mm: {} bars, {:.2f} m, {:.1f} kg\n'.format(
                    dia, dia_stats['count'], dia_stats['length_m'],
                    dia_stats.get('weight_kg', 0.0)
                )
            
            # Mostrar summary en UI
            self.TxtScheduleSummary.Text = u'{} positions, {} bars, {:.1f} m total, {:.1f} kg total'.format(
                stats['total_positions'], stats['total_bars'], stats['total_length_m'],
                stats.get('total_weight_kg', 0.0)
            )
            
            # Preguntar formato de export
            result = forms.CommandSwitchWindow.show(
                [u'Export to CSV', u'Export to Excel (XLSX)', u'Cancel'],
                message=summary_msg,
                title=u'Bar Bending Schedule'
            )
            
            if result == u'Cancel' or result is None:
                return
            
            # Pedir path de salida
            from pyrevit import script
            
            if result == u'Export to CSV':
                ext = 'csv'
                filter_str = 'CSV files (*.csv)|*.csv'
            else:
                ext = 'xlsx'
                filter_str = 'Excel files (*.xlsx)|*.xlsx'
            
            # Nombre por defecto
            doc_name = self.doc.Title or u'RebarSchedule'
            default_name = u'{}_BBS.{}'.format(doc_name, ext)
            
            # Diálogo save
            from System.Windows.Forms import SaveFileDialog, DialogResult
            dlg = SaveFileDialog()
            dlg.Filter = filter_str
            dlg.FileName = default_name
            
            if dlg.ShowDialog() != DialogResult.OK:
                return
            
            output_path = dlg.FileName
            
            # Exportar
            if result == u'Export to CSV':
                success = rebar_schedule.export_csv(schedule_data, output_path)
            else:
                success = rebar_schedule.export_xlsx(schedule_data, output_path)
            
            if success:
                forms.alert(u'Schedule exported successfully to:\n{}'.format(output_path),
                           title=u'Export Complete')
                # Abrir carpeta
                import subprocess
                subprocess.Popen(['explorer', '/select,', output_path])
            else:
                forms.alert(u'Export failed. Check script output for details.',
                           title=u'Export Error', warn_icon=True)
        
        except Exception as e:
            forms.alert(u'Schedule generation failed:\n{}'.format(e),
                       title=u'Error', warn_icon=True)

    def BtnExportBvbs_Click(self, sender, args):
        """
        PHASE F8 — export BVBS (.abs), the interchange format CNC
        bending machines read directly. See rebar_export_bvbs.py's own
        module docstring: the byte-level format has NOT been checked
        against an official BVBS validator or a real machine — the
        alert below repeats that warning to whoever exports the file, so
        it never silently reaches a fabricator as if it were verified.
        """
        if not getattr(self, '_is_loaded', False):
            return
        try:
            schedule_data = rebar_schedule.generate_schedule_data(
                self.doc, batch_id=None, include_finalized=False)
            if not schedule_data:
                forms.alert(u'No NOSA rebars found in the project.',
                           title=u'Export BVBS')
                return

            proceed = forms.alert(
                u'BVBS (.abs) export format has NOT been validated against an '
                u'official BVBS validator or a real bending machine (see '
                u'rebar_export_bvbs.py). Do NOT send this file to a fabricator '
                u'without confirming the format first.\n\n'
                u'Continue and export anyway?',
                title=u'Export BVBS — Unverified Format',
                yes=True, no=True, warn_icon=True)
            if not proceed:
                return

            from System.Windows.Forms import SaveFileDialog, DialogResult
            doc_name = self.doc.Title or u'RebarExport'
            dlg = SaveFileDialog()
            dlg.Filter = 'BVBS files (*.abs)|*.abs'
            dlg.FileName = u'{}.abs'.format(doc_name)
            if dlg.ShowDialog() != DialogResult.OK:
                return
            output_path = dlg.FileName

            count = rebar_export_bvbs.export_bvbs_file(schedule_data, output_path)
            forms.alert(
                u'{} BVBS record(s) written to:\n{}\n\n'
                u'Remember: format not yet validated — see the warning above.'.format(
                    count, output_path),
                title=u'Export Complete')
            import subprocess
            subprocess.Popen(['explorer', '/select,', output_path])
        except Exception as e:
            forms.alert(u'BVBS export failed:\n{}'.format(e),
                       title=u'Error', warn_icon=True)

    # ── section enable/disable ───────────────────────────────────────────

    def IncludeTopMat_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelTopMat.IsEnabled = self.ChkIncludeTopMat.IsChecked == True
        self._update_preview()

    def IncludeSideRebar_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelSideRebar.IsEnabled = self.ChkIncludeSideRebar.IsChecked == True

    def IncludeDowels_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelDowels.IsEnabled = self.ChkIncludeDowels.IsChecked == True

    def IncludePerimeterUBars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelPerimeterUBars.IsEnabled = self.ChkIncludePerimeterUBars.IsChecked == True
        self._update_preview()

    # ── section preview (Phase 2) ────────────────────────────────────────
    # Recomputed and redrawn on every keystroke in a cover/diameter/
    # spacing field, or when Top Mat is toggled — never touches the Revit
    # document (rebar_preview.compute_section_preview is pure Python), so
    # this stays cheap even on a fast typist. Invalid/incomplete input
    # mid-typing is handled by simply skipping the redraw (not erroring
    # the user) until the fields parse again.

    def Preview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_preview()

    def _standard_default_cover_mm(self, element_kind):
        """
        PHASE F2 — the normative fallback cover for element_kind
        ('foundation'/'slab'/'column'/...), used wherever a host has no
        native Rebar Cover of its own to read. Resolves via
        standards.cover_for(self.ra_standard, element_kind) when a
        standard has resolved and declares a cover for that kind;
        falls back to the pre-F2 re_engine.DEFAULT_COVER_MM otherwise
        (unresolved standard, unknown element_kind, or element_kind not
        supplied by an older caller) — never a behaviour change for a
        caller that omits element_kind.
        """
        if element_kind is not None and getattr(self, 'ra_standard', None) is not None:
            std_cover = standards.cover_for(self.ra_standard, element_kind)
            if std_cover is not None:
                return std_cover
        return re_engine.DEFAULT_COVER_MM

    def _preview_cover_mm(self, host, face_type_name, element_kind=None):
        """
        PHASE 3.5.3 item 4 — cover for the illustrative section
        preview: reads the LIVE selected host's own native Rebar Cover
        when one is selected (so the preview reflects reality, not a
        typed guess), or a normative default with no console warning
        when nothing is selected yet (a completely normal state while
        the user is just browsing the tool, not a real cover gap worth
        flagging). PHASE F2 — that default is now
        _standard_default_cover_mm(element_kind).
        """
        default_mm = self._standard_default_cover_mm(element_kind)
        if host is None:
            return default_mm
        return re_engine.get_native_cover_mm(self.doc, host, face_type_name, default_mm)

    def _update_preview(self):
        footings, floors = self._selected_hosts()
        preview_host = (footings + floors)[0] if (footings or floors) else None
        preview_kind = u'foundation' if footings else (u'slab' if floors else None)

        cover = self._preview_cover_mm(preview_host, u'Bottom', preview_kind)
        try:
            dia_x = float(self.TxtDiaX.Text)
            dia_y = float(self.TxtDiaY.Text)
        except (TypeError, ValueError):
            return
        if cover <= 0 or dia_x <= 0 or dia_y <= 0:
            return

        include_top = self.ChkIncludeTopMat.IsChecked == True
        top_cover = top_dia_x = top_dia_y = None
        if include_top:
            try:
                top_cover = self._preview_cover_mm(preview_host, u'Top', preview_kind)
                top_dia_x = float(self.TxtTopDiaX.Text)
                top_dia_y = float(self.TxtTopDiaY.Text)
                if top_cover <= 0 or top_dia_x <= 0 or top_dia_y <= 0:
                    include_top = False
            except (TypeError, ValueError):
                include_top = False  # incomplete top mat mid-typing -- preview bottom mat only

        # Representative section, purely for illustration (see
        # rebar_preview.py's own docstring on why this module never reads
        # real host geometry): width is a fixed round number; thickness
        # is just large enough to show both mats with clear daylight
        # between them, using the same B1/B2/T1/T2 formulas the preview
        # itself applies, plus a visual margin.
        width_mm = 1000.0
        if include_top:
            thickness_mm = max(
                300.0,
                cover + dia_x + dia_y + top_cover + top_dia_x + top_dia_y + 100.0)
        else:
            thickness_mm = max(300.0, (cover + dia_x + dia_y) * 3.0)

        # Perimeter Closure U-Bars only make sense with a top mat present
        # (their back spans bottom-layer Z to top-layer Z) — if the
        # checkbox is checked but Include Top Mat isn't, the PREVIEW
        # simply degrades to showing the main mat alone (RunReinforcement
        # still blocks this combination with a clear error — see
        # _read_inputs) rather than failing the whole preview redraw.
        include_ubars = (self.ChkIncludePerimeterUBars.IsChecked == True) and include_top
        x_anchor_dia = y_anchor_dia = None
        if include_ubars:
            try:
                x_anchor_dia = float(self.TxtXAnchorUBarDia.Text)
                y_anchor_dia = float(self.TxtYAnchorUBarDia.Text)
                if x_anchor_dia <= 0 or y_anchor_dia <= 0:
                    include_ubars = False
            except (TypeError, ValueError):
                include_ubars = False

        # BUG FIX (2026-09-02, live report — "cuando selecciono hooks de
        # 90º... no se ven en el preview") — these checkboxes were
        # already wired to trigger a redraw (Preview_Changed), but
        # nothing downstream ever read their state — compute_section_
        # preview simply had no hooks concept at all until now.
        bottom_hooks = self.ChkBottomHooks.IsChecked == True
        top_hooks = include_top and self.ChkTopHooks.IsChecked == True

        try:
            data = rebar_preview.compute_section_preview(
                width_mm, thickness_mm, cover, dia_x, dia_y,
                include_top, top_cover, top_dia_x, top_dia_y,
                include_perimeter_ubars=include_ubars,
                x_anchor_dia_mm=x_anchor_dia, y_anchor_dia_mm=y_anchor_dia,
                bottom_hooks=bottom_hooks, top_hooks=top_hooks)
        except ValueError:
            return

        self._draw_preview(data)
        self._update_adopted_solution_label(cover, dia_x, dia_y, include_top,
                                            top_cover, top_dia_x, top_dia_y,
                                            include_ubars)

    def _draw_preview(self, data):
        canvas = self.PreviewCanvas
        canvas.Children.Clear()

        section = data['section']
        w_mm = section['width_mm']
        h_mm = section['height_mm']

        # PHASE 2.5 fix — use the Canvas's own FIXED Width/Height (set
        # in ui.xaml, now wrapped in a Viewbox that scales this whole
        # surface to fit) rather than ActualWidth/ActualHeight, which
        # is 0 before the first layout pass and, once laid out, was
        # narrower than the 400px this code used to assume — the exact
        # mismatch that clipped the preview's right edge live.
        cw = canvas.Width
        ch = canvas.Height
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        off_x = cw / 2.0
        off_y = ch - margin

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        # Concrete section outline
        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 1.5
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        # X-Bars (B1/T1) — perpendicular to this section, drawn as dots
        # (you're looking at their cut end).
        for bar in data['bars']:
            dot_d = max(4.0, bar['diameter_mm'] * scale)
            dot = SWS.Ellipse()
            dot.Width = dot_d
            dot.Height = dot_d
            dot.Fill = _PREVIEW_BAR_FILL
            SWC.Canvas.SetLeft(dot, sx(bar['x_mm']) - dot_d / 2.0)
            SWC.Canvas.SetTop(dot, sy(bar['y_mm']) - dot_d / 2.0)
            canvas.Children.Add(dot)

        # Y-Bars (B2/T2) — in-plane with this section, drawn as ONE
        # continuous line resting on/hanging from the X-Bars' dots at
        # the correct Z — the real "weave" a cross-section conveys,
        # rather than Phase 2's dots-for-everything simplification.
        for line_data in data.get('lines', []):
            thickness = max(2.0, line_data['diameter_mm'] * scale)
            seg = SWS.Line()
            seg.X1, seg.Y1 = sx(line_data['x0_mm']), sy(line_data['y_mm'])
            seg.X2, seg.Y2 = sx(line_data['x1_mm']), sy(line_data['y_mm'])
            seg.Stroke = _PREVIEW_BAR_FILL
            seg.StrokeThickness = thickness
            canvas.Children.Add(seg)

        # 90° hooks (Phase 2.6, 2026-09-02, live report — "Include 90°
        # Hooks" had no visible effect) — a short bend stub off each end
        # of the B2/T2 line (see compute_section_preview's own docstring
        # for why B1/T1's dots have nothing to show here).
        for hook in data.get('hooks', []):
            thickness = max(2.0, hook['diameter_mm'] * scale)
            seg = SWS.Line()
            seg.X1, seg.Y1 = sx(hook['x0_mm']), sy(hook['y0_mm'])
            seg.X2, seg.Y2 = sx(hook['x1_mm']), sy(hook['y1_mm'])
            seg.Stroke = _PREVIEW_BAR_FILL
            seg.StrokeThickness = thickness
            canvas.Children.Add(seg)

        # Layer labels (B1/B2/T1/T2), one per distinct layer present
        label_rows = [(bar['layer'], bar['y_mm']) for bar in data['bars']]
        label_rows += [(ln['layer'], ln['y_mm']) for ln in data.get('lines', [])]
        seen_layers = set()
        for layer, y_mm in label_rows:
            if layer in seen_layers:
                continue
            seen_layers.add(layer)
            lbl = SWC.TextBlock()
            lbl.Text = layer
            lbl.FontSize = 9
            lbl.Opacity = 0.7
            SWC.Canvas.SetLeft(lbl, sx(w_mm / 2.0) + 4.0)
            SWC.Canvas.SetTop(lbl, sy(y_mm) - 6.0)
            canvas.Children.Add(lbl)

        # Perimeter Closure U-Bars (Phase 2.1) — each profile is a
        # 4-point open polyline ([leg, back, leg], matching
        # footing_rebar.build_perimeter_closure_ubar_sets' own curve
        # chain), drawn as 3 connected Line segments since WPF's
        # Polyline point-collection isn't otherwise needed anywhere
        # else in this module.
        for ubar in data.get('perimeter_ubars', []):
            stroke = (_PREVIEW_UBAR_PRIMARY_STROKE if ubar['style'] == 'primary'
                      else _PREVIEW_UBAR_WEAVE_STROKE)
            thickness = max(1.5, ubar['diameter_mm'] * scale * 0.6)
            pts = ubar['points']
            for i in range(len(pts) - 1):
                x1_mm, y1_mm = pts[i]
                x2_mm, y2_mm = pts[i + 1]
                seg = SWS.Line()
                seg.X1, seg.Y1 = sx(x1_mm), sy(y1_mm)
                seg.X2, seg.Y2 = sx(x2_mm), sy(y2_mm)
                seg.Stroke = stroke
                seg.StrokeThickness = thickness
                canvas.Children.Add(seg)

    def _update_adopted_solution_label(self, cover, dia_x, dia_y, include_top,
                                        top_cover, top_dia_x, top_dia_y,
                                        include_ubars=False):
        text = (u'Adopted Solution — Bottom: {:.0f}mm cover, Ø{:.0f}/Ø{:.0f} '
                u'(B1/B2)').format(cover, dia_x, dia_y)
        if include_top:
            text += (u'  |  Top: {:.0f}mm cover, Ø{:.0f}/Ø{:.0f} '
                     u'(T1/T2)').format(top_cover, top_dia_x, top_dia_y)
        if include_ubars:
            text += (u'  |  Perimeter Closure U-Bars active — compliant with the '
                     u'B1/B2/T1/T2 layer hierarchy.')
        self.TxtAdoptedSolution.Text = text

    # ── selection ─────────────────────────────────────────────────────────

    def _selected_hosts(self):
        """
        Splits the current selection into (footings, floors) by category
        — OST_StructuralFoundation and OST_Floors respectively. Anything
        else in the selection is silently ignored (not an error — the
        user may well have other elements selected for an unrelated
        reason); the backend then dispatches each group to its own
        engine (footing_rebar vs floor_rebar) from the SAME shared form.
        """
        ids = self.uidoc.Selection.GetElementIds()
        footings, floors = [], []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            cat_id = get_id_value(elem.Category.Id)
            if cat_id == _cat_id('OST_StructuralFoundation'):
                footings.append(elem)
            elif cat_id == _cat_id('OST_Floors'):
                floors.append(elem)
        return footings, floors

    # ── input parsing ────────────────────────────────────────────────────

    def _read_number(self, text, label, errors):
        try:
            value = float(text)
        except (TypeError, ValueError):
            errors.append(u'"{}" must be a number.'.format(label))
            return None
        if value <= 0:
            errors.append(u'"{}" must be greater than zero.'.format(label))
            return None
        return value

    def _read_inputs(self):
        """
        Reads every field across all sections. Returns a dict on
        success, or None (after showing one alert listing every problem
        found) if any required field is missing/non-numeric/non-positive.
        Fields inside a section whose checkbox is unchecked are not read
        at all.
        """
        errors = []
        values = {}

        # PHASE 3.5.3 item 4 — cover is no longer read here: it's
        # resolved per-host from native Rebar Cover in _process_footing
        # / _process_floor, since each selected host can have its own
        # configured cover.
        values['dia_x'] = self._read_number(self.TxtDiaX.Text, u'Bottom diameter X', errors)
        values['dia_y'] = self._read_number(self.TxtDiaY.Text, u'Bottom diameter Y', errors)
        values['spacing'] = self._read_number(self.TxtSpacing.Text, u'Bottom spacing', errors)
        values['bottom_hooks'] = self.ChkBottomHooks.IsChecked == True
        values['max_stock_length'] = self._read_number(
            self.TxtMaxStockLength.Text, u'Max stock length', errors)

        values['include_top_mat'] = self.ChkIncludeTopMat.IsChecked == True
        if values['include_top_mat']:
            values['top_dia_x'] = self._read_number(self.TxtTopDiaX.Text, u'Top diameter X', errors)
            values['top_dia_y'] = self._read_number(self.TxtTopDiaY.Text, u'Top diameter Y', errors)
            values['top_spacing'] = self._read_number(self.TxtTopSpacing.Text, u'Top spacing', errors)
            values['top_hooks'] = self.ChkTopHooks.IsChecked == True

        values['include_side_rebar'] = self.ChkIncludeSideRebar.IsChecked == True
        if values['include_side_rebar']:
            values['side_diameter'] = self._read_number(
                self.TxtSideDiameter.Text, u'Side bar diameter', errors)
            values['side_spacing'] = self._read_number(
                self.TxtSideSpacing.Text, u'Side rebar spacing', errors)

        values['include_dowels'] = self.ChkIncludeDowels.IsChecked == True
        if values['include_dowels']:
            values['dowel_diameter'] = self._read_number(
                self.TxtDowelDiameter.Text, u'Dowel diameter', errors)
            try:
                values['dowel_count'] = int(self.CmbDowelCount.Text)
            except (TypeError, ValueError):
                errors.append(u'Dowel count must be 4 or 8.')
                values['dowel_count'] = None
            if values['dowel_count'] not in (4, 8):
                errors.append(u'Dowel count must be 4 or 8.')
            values['dowel_anchor'] = self._read_number(
                self.TxtDowelAnchor.Text, u'Dowel anchor length', errors)
            values['dowel_splice'] = self._read_number(
                self.TxtDowelSplice.Text, u'Dowel splice length', errors)
            values['dowel_col_width'] = self._read_number(
                self.TxtDowelColWidth.Text, u'Dowel column width', errors)
            values['dowel_col_depth'] = self._read_number(
                self.TxtDowelColDepth.Text, u'Dowel column depth', errors)
            # Dowels under a column follow the verticals the Columns tab would give it (T2.15b).
            try:
                values['dowel_col_bar_count'] = int(float(self.TxtColBarCount.Text))
                values['dowel_col_bar_dia'] = float(self.TxtColBarDia.Text)
                values['dowel_col_link_dia'] = float(self.TxtColLinkDia.Text)
            except (TypeError, ValueError):
                values['dowel_col_bar_count'] = None

        values['include_perimeter_ubars'] = self.ChkIncludePerimeterUBars.IsChecked == True
        if values['include_perimeter_ubars']:
            if not values['include_top_mat']:
                errors.append(u'Perimeter Closure U-Bars require "Include Top Mat" '
                              u'to also be checked — the closure bars anchor '
                              u'between the bottom and top mats.')
            values['x_anchor_ubar_dia'] = self._read_number(
                self.TxtXAnchorUBarDia.Text, u'X-Bars Anchoring U-Bar diameter', errors)
            values['x_anchor_ubar_spacing'] = self._read_number(
                self.TxtXAnchorUBarSpacing.Text, u'X-Bars Anchoring U-Bar spacing', errors)
            values['y_anchor_ubar_dia'] = self._read_number(
                self.TxtYAnchorUBarDia.Text, u'Y-Bars Anchoring U-Bar diameter', errors)
            values['y_anchor_ubar_spacing'] = self._read_number(
                self.TxtYAnchorUBarSpacing.Text, u'Y-Bars Anchoring U-Bar spacing', errors)

        values['generate_sections'] = self.ChkGenerateSections.IsChecked == True

        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    # ── main action ───────────────────────────────────────────────────────

    def RunReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'footings_floors', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_reinforcement_result(self, footings, floors, summary):
        lines = [
            u'{} footing(s), {} floor(s) processed.'.format(len(footings), len(floors)),
            u'{} Rebar element(s) created (sets count as one each).'.format(summary['created']),
            u'{} tag(s) created.'.format(summary['tags']),
            u'{} detail section(s) created.'.format(summary['sections']),
        ]
        if summary['errors']:
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — used to cap at 12 + "...and N more",
            # reported live as making a longer run's own tracking log
            # impossible to review in full. TxtResult is now a scrollable,
            # read-only TextBox (see ui.xaml) — no reason left to truncate.
            lines.extend(summary['errors'])
        self.TxtResult.Text = u'\n'.join(lines)

    # ── bar type resolution ───────────────────────────────────────────────

    def _resolve_bar_types(self, values, errors):
        """
        Looks up every RebarBarType this run will need, once, up front —
        so a missing type is reported ONCE per diameter (not once per
        Rebar Set) and the caller can skip just that direction/mat/dowel/
        side rather than aborting the whole run.
        """
        diameters = {values['dia_x'], values['dia_y']}
        if values['include_top_mat']:
            diameters.add(values['top_dia_x'])
            diameters.add(values['top_dia_y'])
        if values['include_side_rebar']:
            diameters.add(values['side_diameter'])
        if values['include_dowels']:
            diameters.add(values['dowel_diameter'])
        if values['include_perimeter_ubars']:
            diameters.add(values['x_anchor_ubar_dia'])
            diameters.add(values['y_anchor_ubar_dia'])

        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt
        return bar_types

    def _resolve_hook_type(self, values, errors):
        """
        A single 90° RebarHookType lookup for DOWELS only — Phase 5.4
        moved mat bars to explicit full-depth U-bar leg geometry (see
        footing_rebar.py's module docstring), so RebarHookType is no
        longer used for mats at all. Returns None (with ONE warning
        appended to `errors`) if dowels were requested but no 90° hook
        type exists in the project — dowels are then created straight
        (no hook) instead of aborting.
        """
        if not values['include_dowels']:
            return None
        hook_type = re_engine.get_hook_type_by_angle(self.doc, 90.0)
        if hook_type is None:
            errors.append(u'No 90° RebarHookType found in this project — dowels '
                          u'will be created straight (no hook) instead.')
        return hook_type

    # ── bar/set creation ──────────────────────────────────────────────────

    def _create_side_rebar_set(self, wrapper, host, side_rebar, bar_type, errors, created_rebars):
        if bar_type is None:
            return
        rebar = wrapper.create_rebar_set(
            host, side_rebar['curves'], bar_type,
            side_rebar['spacing_mm'], side_rebar['array_length_mm'],
            normal=side_rebar['face_normal'], style=DBS.RebarStyle.StirrupTie,
            transaction_name=u'NOSA — Create Footing Side Rebar')
        if rebar is None:
            errors.append(u'Footing {}: side rebar — {}'.format(get_id_value(host.Id), wrapper.last_error))
        else:
            self._stamp_layer(rebar, u'side')
            created_rebars.append(rebar)
            if wrapper.last_error:
                errors.append(u'Footing {}: side rebar — {}'.format(get_id_value(host.Id), wrapper.last_error))

    def _create_dowel_bars(self, wrapper, host, dowels, bar_type, hook_type, errors, created_rebars):
        """
        Dowels stay individual Rebar elements (not a Set): a 4/8-corner
        square isn't a single-direction linear array
        ShapeDrivenAccessor can represent, so this is unaffected by
        Phase 5.1's Rebar Set refactor — see footing_rebar.py's module
        docstring.
        """
        if bar_type is None:
            return
        for line, normal in zip(dowels['bars'], dowels['normals']):
            rebar = wrapper.create_from_curves(
                host, [line], bar_type,
                start_hook=hook_type, end_hook=None,
                start_hook_orientation=_HOOK_ORIENTATION if hook_type else None,
                normal=normal,
                transaction_name=u'NOSA — Create Footing Dowel')
            if rebar is None:
                errors.append(u'Footing {}: dowel — {}'.format(get_id_value(host.Id), wrapper.last_error))
            else:
                self._stamp_layer(rebar, u'dowel')
                created_rebars.append(rebar)
        for column_id in dowels.get('skipped_columns', []):
            errors.append(u'Footing {}: no dowels under column {} — it already has NOSA dowels '
                          u'or foundation starters.'.format(get_id_value(host.Id), get_id_value(column_id)))
        if dowels.get('wall_footing'):
            errors.append(u'Footing {}: no dowels — it is a strip footing with no column above; '
                          u'use the wall foundation starters (Walls tab) instead.'.format(
                              get_id_value(host.Id)))
        for column_id in dowels.get('fallback_columns', []):
            errors.append(u'Footing {}: could not lay out the Columns-tab verticals of column {} — '
                          u'dowels placed on its bar line (Dowel Count) instead.'.format(
                              get_id_value(host.Id), get_id_value(column_id)))
        embedded = dowels.get('embedded_mm')
        if dowels['bars'] and embedded is not None and embedded < dowels.get('anchor_length_mm', 0.0):
            errors.append(u'Footing {}: dowels embedded only {:.0f} mm, less than the {:.0f} mm '
                          u'anchorage asked for — check the footing depth.'.format(
                              get_id_value(host.Id), embedded, dowels['anchor_length_mm']))

    def _create_foundation_starter_bars(self, wrapper, host, starters, bar_type, hook_type,
                                         label, errors, created_rebars):
        """
        PHASE F7.18 (2026-09-02, explicit request) — companion to
        _create_dowel_bars for column_rebar.build_column_foundation_
        starters / wall_rebar.build_wall_foundation_starters: individual
        Rebar elements (same reasoning as dowels — a handful of bars at
        real, possibly-irregular positions, not a single-direction
        array), hosted on the COLUMN/WALL itself (not the foundation
        found below it — Revit's own `host` argument is an association
        for cover/grouping, not a geometric clip, matching how a
        perimeter closure U-bar already spans between two different
        structural elements conceptually), with the SAME start-hook
        convention _create_dowel_bars uses.

        `starters['skipped']` (bar positions where no foundation was
        detected below) is reported as ONE summary warning, not one
        per position — this is routine for a column/wall that doesn't
        land on a foundation everywhere (e.g. only some columns in a
        grid have their own footing modelled yet), not a per-bar error.
        """
        if bar_type is None:
            return
        for line, normal, foundation in zip(starters.get('bars', []), starters.get('normals', []),
                                            starters.get('hosts', [])):
            rebar = wrapper.create_from_curves(
                foundation, [line], bar_type,
                start_hook=hook_type, end_hook=None,
                start_hook_orientation=_HOOK_ORIENTATION if hook_type else None,
                normal=normal,
                transaction_name=u'NOSA — Create {} Foundation Starter'.format(label))
            if rebar is None:
                errors.append(u'{} {}: foundation starter — {}'.format(
                    label, get_id_value(host.Id), wrapper.last_error))
            else:
                self._stamp_layer(rebar, u'foundation_starter')
                created_rebars.append(rebar)
        if starters.get('assumed_mat'):
            errors.append(u'{} {}: no NOSA bottom mat found in the foundation below — {} starter '
                          u'foot/feet placed on an assumed 2-layer mat; arm the foundation first '
                          u'for an exact fit.'.format(label, get_id_value(host.Id), starters['assumed_mat']))
        short = starters.get('short_anchor_mm', [])
        if short:
            errors.append(u'{} {}: {} starter(s) embedded only {:.0f} mm in the foundation, less '
                          u'than the {:.0f} mm anchorage asked for — check the foundation depth.'.format(
                              label, get_id_value(host.Id), len(short), min(short),
                              starters.get('anchor_length_mm', 0.0)))
        skipped = starters.get('skipped', 0)
        if skipped:
            errors.append(u'{} {}: {} starter position(s) skipped — no foundation '
                          u'(isolated/strip footing or floor/mat slab) detected '
                          u'directly below.'.format(label, get_id_value(host.Id), skipped))

    def _stamp_layer(self, rebar, layer):
        """
        FEATURE (2026-09-02, explicit request) — F3's own known gap
        since it was written: generators never stamped
        `NOSA_Rebar_Layer` after creating a Rebar, so every bar fell
        back to "uncategorized" in `rebar_marking.assign_layers_and_
        lengths` regardless of what it actually was (vertical mesh,
        stirrup, top mat, closure U-bar, ...). Called right after each
        creation call across every typology below, with a short code
        identifying what that specific bar/Set is — never raises (same
        "fail warning, not exploding" contract as shared_params.write
        itself).

        Only RECORDS the layer: writing it here happened outside any
        transaction (each bar's own creation transaction has already
        committed), so Revit rejected every write and all bars ended up
        "uncategorized" (verified live 2026-09-29, 123/123 bars).
        RebarBatch writes the recorded layers inside its provenance
        transaction and reports any failure.
        """
        if rebar is None or not layer:
            return
        self._pending_layers[get_id_value(rebar.Id)] = layer

    def _create_grouped_bars(self, wrapper, host, grouped, bar_type, errors, created_rebars, label,
                              layer=None):
        """
        Phase 2.3 — floors' main-grid bars and perimeter closure U-bars
        come back from floor_rebar.py as {'sets': [...], 'bars': [...]}:
        a `set` entry is a maximal run of rows sharing an identical
        clipped shape, created as ONE Rebar Set via create_rebar_set
        (MRA/schedule-friendly, the same mechanism footings already
        use); a `bar` entry is a genuinely one-off segment (an
        irregular transition row near a chamfer/hole edge). Either
        entry may carry an optional 'style' of 'StirrupTie' (a closed
        link replacing two colliding perimeter U-bars in a narrow zone
        — see floor_rebar.py's Phase 2.3 item 4) instead of the default
        open (Standard) shape.

        PHASE 3.5 REVERSAL — MRA/Rebar Sets are NON-NEGOTIABLE. The
        previous turn's "fix" (routing everything through
        create_from_curves for correct Shape 21/01 naming) is REVERTED:
        it silently traded away Multi-Rebar Annotation and schedule
        grouping — genuinely load-bearing for production drawings — to
        chase a shape name in the model tree that has no drawing-side
        consequence. The correct priority order, restated: a `set`
        entry ALWAYS tries create_rebar_set first
        (SetLayoutAsMaximumSpacing — MRA-friendly, one element for a
        whole uniform run); if that Set's own propagation fails, OR for
        a standalone irregular `bars` entry (a chamfer/hole transition
        row a Set cannot represent), the fallback is
        create_freeform_group — bundling the whole remainder into ONE
        MRA-taggable Rebar element — NOT a loop of individual
        create_from_curves bars. If Revit reports that bundled element
        as generic "Shape 00", THAT IS ACCEPTED: one boundable,
        schedulable Shape-00 Set beats a thousand named-but-ungroupable
        loose bars that sink the model. Only if create_freeform_group
        ITSELF fails does this fall back further to individual
        create_from_curves bars, per row — the true last resort, not
        the default path for irregular geometry.
        """
        if bar_type is None:
            return
        style_map = {'StirrupTie': DBS.RebarStyle.StirrupTie}
        for s in grouped.get('sets', []):
            style = style_map.get(s.get('style'))
            rebar = wrapper.create_rebar_set(
                host, s['curves'], bar_type, s['spacing_mm'], s['array_length_mm'],
                normal=s['normal'], style=style,
                transaction_name=u'NOSA — Create {}'.format(label))
            propagated = rebar is not None and not (
                wrapper.last_error and u'propagation failed' in wrapper.last_error)
            if propagated:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)
                continue

            if rebar is not None:
                # A single, un-propagated bar was created under the Set
                # attempt — remove it before rebuilding the run via
                # FreeForm, so the two paths never both leave geometry
                # behind for the same run.
                try:
                    with revit.Transaction(u'NOSA — Remove Unpropagated Bar'):
                        self.doc.Delete(rebar.Id)
                except Exception:
                    pass

            materialized = s.get('materialized_bars', [])
            # PHASE 3.5.8 (2026-09-02, explicit user request) — hole-closure
            # U-bars must report their real Shape (e.g. 21), never generic
            # "Shape 00": for a `set` FLAGGED is_hole, skip the FreeForm
            # fallback entirely and go straight to individual
            # create_from_curves bars if the Set itself didn't propagate —
            # losing MRA/schedule grouping for just this hole's run, in
            # exchange for a correctly-named shape, per explicit user
            # choice over the codebase's general "grouping > shape name"
            # default (still used everywhere else — outer perimeter sets
            # included).
            if len(materialized) >= 2 and not s.get('is_hole'):
                curve_groups = [b['curves'] for b in materialized]
                ff_rebar = wrapper.create_freeform_group(
                    host, curve_groups, bar_type,
                    transaction_name=u'NOSA — Create {} (FreeForm fallback)'.format(label))
                if ff_rebar is not None:
                    self._stamp_layer(ff_rebar, layer)
                    created_rebars.append(ff_rebar)
                    continue
                errors.append(u'Host {}: {} (set) — Set propagation failed and the '
                              u'FreeForm fallback also failed ({}); created as '
                              u'individual bars (not MRA-groupable).'.format(
                                  get_id_value(host.Id), label, wrapper.last_error))
                for b in materialized:
                    rb = wrapper.create_from_curves(
                        host, b['curves'], bar_type, normal=b['normal'], style=style,
                        transaction_name=u'NOSA — Create {}'.format(label))
                    if rb is None:
                        errors.append(u'Host {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
                    else:
                        self._stamp_layer(rb, layer)
                        created_rebars.append(rb)
            elif materialized:
                # is_hole Set whose propagation failed — per explicit user
                # choice above, go straight to individual create_from_curves
                # (real Shape code, e.g. 21) instead of FreeForm (Shape 00).
                errors.append(u'Host {}: {} (set, hole closure) — Set '
                              u'propagation failed ({}); creating individual '
                              u'bars to keep the real Shape code (not '
                              u'MRA-groupable).'.format(
                                  get_id_value(host.Id), label, wrapper.last_error))
                for b in materialized:
                    rb = wrapper.create_from_curves(
                        host, b['curves'], bar_type, normal=b['normal'], style=style,
                        transaction_name=u'NOSA — Create {}'.format(label))
                    if rb is None:
                        errors.append(u'Host {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
                    else:
                        self._stamp_layer(rb, layer)
                        created_rebars.append(rb)
            else:
                errors.append(u'Host {}: {} (set) — {}'.format(
                    get_id_value(host.Id), label, wrapper.last_error))

        loose_bars = grouped.get('bars', [])
        # PHASE 3.5.8 (2026-09-02) — hole-closure U-bars (is_hole=True)
        # never enter the FreeForm bundle, even when there are 2+ of them:
        # per explicit user choice, they always go through create_from_curves
        # below so they report their real Shape (e.g. 21) instead of the
        # generic "Shape 00" FreeForm produces. Only non-hole loose bars
        # (irregular perimeter transition rows) keep the original
        # grouping-over-shape-name trade-off.
        freeform_candidates = [b for b in loose_bars
                                if b.get('style') is None and not b.get('is_hole')]
        fallback_bars = [b for b in loose_bars
                          if b.get('style') is not None or b.get('is_hole')]

        if len(freeform_candidates) >= 2:
            curve_groups = [b['curves'] for b in freeform_candidates]
            rebar = wrapper.create_freeform_group(
                host, curve_groups, bar_type,
                transaction_name=u'NOSA — Create {} (FreeForm)'.format(label))
            if rebar is not None:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)
            else:
                errors.append(u'Host {}: {} — FreeForm grouping unavailable ({}); '
                              u'created as individual bars instead (not MRA-groupable).'.format(
                                  get_id_value(host.Id), label, wrapper.last_error))
                fallback_bars = fallback_bars + freeform_candidates
        else:
            fallback_bars = fallback_bars + freeform_candidates

        for b in fallback_bars:
            style = style_map.get(b.get('style'))
            rebar = wrapper.create_from_curves(
                host, b['curves'], bar_type, normal=b['normal'], style=style,
                transaction_name=u'NOSA — Create {}'.format(label))
            if rebar is None:
                errors.append(u'Host {}: {} — {}'.format(
                    get_id_value(host.Id), label, wrapper.last_error))
            else:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)

    # ── detail sections ───────────────────────────────────────────────────

    def _create_detail_sections(self, footings, errors):
        vft = rebar_detailing.get_detail_section_view_family_type(self.doc)
        if vft is None:
            errors.append(u'No Detail Section view type found in this project — '
                          u'sections were not created.')
            return 0

        created = 0
        with revit.Transaction(u'NOSA — Footing Detail Sections'):
            for host in footings:
                for axis in ('X', 'Y'):
                    section = rebar_detailing.create_rebar_detail_section(
                        self.doc, host, vft.Id, cut_axis=axis)
                    if section is None:
                        errors.append(u'Footing {}: could not create the {}-axis '
                                      u'detail section.'.format(get_id_value(host.Id), axis))
                    else:
                        created += 1
        return created

    # ── orchestration ─────────────────────────────────────────────────────

    def _process_footing(self, host, values, wrapper, bar_types, hook_type, errors, created_rebars):
        """
        Full footing pipeline for one host: bottom/top mat, plus the
        footing-only extras (side rebar, dowels) if requested. Detail
        sections are handled separately in _run_reinforcement (they're
        batched across all footings in their own Transaction).

        PHASE 3.5.3 item 4 — cover is no longer a UI value shared
        across every selected host: it is read from EACH host's own
        native Rebar Cover (re_engine.get_native_cover_mm), since two
        footings in the same selection can genuinely have different
        configured covers.
        """
        bottom_cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Bottom', self._standard_default_cover_mm(u'foundation'))
        top_cover_mm = (re_engine.get_native_cover_mm(
                            self.doc, host, u'Top', self._standard_default_cover_mm(u'foundation'))
                        if values['include_top_mat'] else None)
        reinforcement = footing_rebar.build_footing_reinforcement(
            self.doc, host,
            bottom_cover_mm=bottom_cover_mm,
            bottom_dia_x_mm=values['dia_x'],
            bottom_dia_y_mm=values['dia_y'],
            bottom_spacing_mm=values['spacing'],
            bottom_hooks=values['bottom_hooks'],
            include_top_mat=values['include_top_mat'],
            top_cover_mm=top_cover_mm,
            top_dia_x_mm=values.get('top_dia_x'),
            top_dia_y_mm=values.get('top_dia_y'),
            top_spacing_mm=values.get('top_spacing'),
            top_hooks=values.get('top_hooks', False),
            include_dowels=values['include_dowels'],
            dowel_count=values.get('dowel_count'),
            dowel_diameter_mm=values.get('dowel_diameter'),
            dowel_anchor_length_mm=values.get('dowel_anchor'),
            dowel_splice_length_mm=values.get('dowel_splice'),
            dowel_column_width_mm=values.get('dowel_col_width', 400.0),
            dowel_column_depth_mm=values.get('dowel_col_depth', 400.0),
            dowel_column_bar_count=values.get('dowel_col_bar_count'),
            dowel_column_bar_dia_mm=values.get('dowel_col_bar_dia'),
            dowel_column_link_dia_mm=values.get('dowel_col_link_dia'),
            include_side_rebar=values['include_side_rebar'],
            side_diameter_mm=values.get('side_diameter'),
            side_spacing_mm=values.get('side_spacing'),
            include_perimeter_closure_ubars=values['include_perimeter_ubars'],
            x_anchor_ubar_dia_mm=values.get('x_anchor_ubar_dia'),
            x_anchor_ubar_spacing_mm=values.get('x_anchor_ubar_spacing'),
            y_anchor_ubar_dia_mm=values.get('y_anchor_ubar_dia'),
            y_anchor_ubar_spacing_mm=values.get('y_anchor_ubar_spacing'),
            max_stock_length_mm=values['max_stock_length'],
            std=getattr(self, 'ra_standard', None))

        # PHASE 3.5.7 item 3 — bottom_mat/top_mat/perimeter_closure_ubars
        # now come from footing_rebar's topology-aware builders (real
        # boundary + hole clipping, footing_rebar.build_mat_bars_topology
        # / build_perimeter_closure_ubars_topology), in the SAME
        # {'sets':[...],'bars':[...]} shape floors already use — created
        # via the SAME _create_grouped_bars method, not the old
        # single-Set _create_mat_bar_set/_create_perimeter_closure_ubars
        # (which assumed one uniform Set spans the whole rectangular
        # footing with no holes).
        bottom = reinforcement['bottom_mat']
        self._create_grouped_bars(
            wrapper, host, bottom['along_x'], bar_types.get(values['dia_x']),
            errors, created_rebars, u'Footing Bottom Mat (B1)', layer=u'bottom_x')
        self._create_grouped_bars(
            wrapper, host, bottom['along_y'], bar_types.get(values['dia_y']),
            errors, created_rebars, u'Footing Bottom Mat (B2)', layer=u'bottom_y')

        if reinforcement['top_mat'] is not None:
            top = reinforcement['top_mat']
            self._create_grouped_bars(
                wrapper, host, top['along_x'], bar_types.get(values['top_dia_x']),
                errors, created_rebars, u'Footing Top Mat (T1)', layer=u'top_x')
            self._create_grouped_bars(
                wrapper, host, top['along_y'], bar_types.get(values['top_dia_y']),
                errors, created_rebars, u'Footing Top Mat (T2)', layer=u'top_y')

        if reinforcement.get('perimeter_closure_ubars') is not None:
            closure = reinforcement['perimeter_closure_ubars']
            self._create_grouped_bars(
                wrapper, host, closure['x_bars'], bar_types.get(values.get('x_anchor_ubar_dia')),
                errors, created_rebars, u'Footing Perimeter Closure U-Bar (X-anchor)',
                layer=u'closure_x')
            self._create_grouped_bars(
                wrapper, host, closure['y_bars'], bar_types.get(values.get('y_anchor_ubar_dia')),
                errors, created_rebars, u'Footing Perimeter Closure U-Bar (Y-anchor)',
                layer=u'closure_y')
            debug_failed_edges = closure.get('debug_failed_edges')
            if debug_failed_edges:
                errors.append(u'Footing {}: {} perimeter closure U-bar edge(s) failed — '
                              u'see the pyRevit console output for exact coordinates.'.format(
                                  get_id_value(host.Id), len(debug_failed_edges)))

        if reinforcement['side_rebar'] is not None:
            self._create_side_rebar_set(
                wrapper, host, reinforcement['side_rebar'],
                bar_types.get(values.get('side_diameter')), errors, created_rebars)

        if reinforcement['dowels'] is not None:
            self._create_dowel_bars(
                wrapper, host, reinforcement['dowels'],
                bar_types.get(values.get('dowel_diameter')),
                hook_type, errors, created_rebars)

    def _process_floor(self, host, values, wrapper, bar_types, errors, created_rebars):
        """
        Floor pipeline for one host (Phase 2.2 — see floor_rebar.py's
        module docstring): real topology, individual Rebar elements
        (not Sets — a floor's main grid and closure U-bars can have
        variable-length, hole-split rows that a Set cannot represent).

        PHASE 3.5.3 item 4 — cover read from THIS host's own native
        Rebar Cover, same as _process_footing — see that method's own
        note.
        """
        bottom_cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Bottom', self._standard_default_cover_mm(u'slab'))
        top_cover_mm = (re_engine.get_native_cover_mm(
                            self.doc, host, u'Top', self._standard_default_cover_mm(u'slab'))
                        if values['include_top_mat'] else None)
        reinforcement = floor_rebar.build_floor_reinforcement(
            self.doc, host,
            bottom_cover_mm=bottom_cover_mm,
            bottom_dia_x_mm=values['dia_x'],
            bottom_dia_y_mm=values['dia_y'],
            bottom_spacing_mm=values['spacing'],
            bottom_hooks=values['bottom_hooks'],
            include_top_mat=values['include_top_mat'],
            top_cover_mm=top_cover_mm,
            top_dia_x_mm=values.get('top_dia_x'),
            top_dia_y_mm=values.get('top_dia_y'),
            top_spacing_mm=values.get('top_spacing'),
            top_hooks=values.get('top_hooks', False),
            include_perimeter_closure_ubars=values['include_perimeter_ubars'],
            x_anchor_ubar_dia_mm=values.get('x_anchor_ubar_dia'),
            x_anchor_ubar_spacing_mm=values.get('x_anchor_ubar_spacing'),
            y_anchor_ubar_dia_mm=values.get('y_anchor_ubar_dia'),
            y_anchor_ubar_spacing_mm=values.get('y_anchor_ubar_spacing'),
            max_stock_length_mm=values['max_stock_length'],
            std=getattr(self, 'ra_standard', None))

        bottom = reinforcement['bottom_mat']
        self._create_grouped_bars(
            wrapper, host, bottom['along_x'], bar_types.get(values['dia_x']),
            errors, created_rebars, u'Floor Bottom Mat (B1)', layer=u'bottom_x')
        self._create_grouped_bars(
            wrapper, host, bottom['along_y'], bar_types.get(values['dia_y']),
            errors, created_rebars, u'Floor Bottom Mat (B2)', layer=u'bottom_y')

        if reinforcement['top_mat'] is not None:
            top = reinforcement['top_mat']
            self._create_grouped_bars(
                wrapper, host, top['along_x'], bar_types.get(values['top_dia_x']),
                errors, created_rebars, u'Floor Top Mat (T1)', layer=u'top_x')
            self._create_grouped_bars(
                wrapper, host, top['along_y'], bar_types.get(values['top_dia_y']),
                errors, created_rebars, u'Floor Top Mat (T2)', layer=u'top_y')

        if reinforcement.get('perimeter_closure_ubars') is not None:
            closure = reinforcement['perimeter_closure_ubars']
            self._create_grouped_bars(
                wrapper, host, closure['x_bars'], bar_types.get(values.get('x_anchor_ubar_dia')),
                errors, created_rebars, u'Floor Perimeter Closure U-Bar (X-anchor)',
                layer=u'closure_x')
            self._create_grouped_bars(
                wrapper, host, closure['y_bars'], bar_types.get(values.get('y_anchor_ubar_dia')),
                errors, created_rebars, u'Floor Perimeter Closure U-Bar (Y-anchor)',
                layer=u'closure_y')
            debug_failed_edges = closure.get('debug_failed_edges')
            if debug_failed_edges:
                # PHASE 3.5.4 item 2 FIX — no longer draws ModelCurve
                # elements here: creating one without a SketchPlane
                # that exactly contains the curve threw a hard .NET
                # exception mid-Transaction, corrupting the whole
                # floor's reinforcement run. Console-only telemetry —
                # floor_rebar.py's own WARNING print (with the exact
                # p0/p1/bz/tz/inward_normal) already carries everything
                # needed to diagnose a failed edge.
                errors.append(u'Floor {}: {} perimeter closure U-bar edge(s) failed — '
                              u'see the pyRevit console output for exact coordinates.'.format(
                                  get_id_value(host.Id), len(debug_failed_edges)))

        if reinforcement.get('n_small_holes_ignored'):
            errors.append(u'Floor {}: {} small opening(s) (≤200x200mm) ignored — '
                          u'main reinforcement runs through uncut, by design.'.format(
                              get_id_value(host.Id), reinforcement['n_small_holes_ignored']))

    def _run_reinforcement(self, footings, floors, values):
        """
        PHASE F1 — the outer TransactionGroup this docstring used to
        describe is now owned by rebar_batch.RebarBatch.run (its own
        caller — see the Execute() handler), not this method: Revit
        does not support a nested/concurrent TransactionGroup on the
        same document, and RebarBatch's own group now also needs to
        cover the provenance-stamping pass that runs AFTER this method
        returns. This method's own geometry generation is completely
        unchanged — per-host curve generation (pure geometry, no
        Transaction), then one RebarWrapper call per Rebar Set / dowel
        bar (each still opens its own inner Transaction, exactly as
        before), then one Transaction to tag every element created
        (footings and floors together), then (if requested) one
        Transaction to create detail sections (footings only).

        Returns:
            (created_rebars, summary) — the actual list of DB.Element
            objects just created (PHASE F1: newly returned, so
            RebarBatch can stamp provenance on each one — it was
            already being built internally, just never returned before),
            and the same summary dict shape as always
            ({'created', 'tags', 'sections', 'errors'}).
        """
        errors = []
        bar_types = self._resolve_bar_types(values, errors)
        hook_type = self._resolve_hook_type(values, errors)

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []

        for host in footings:
            try:
                self._process_footing(host, values, wrapper, bar_types, hook_type,
                                      errors, created_rebars)
            except Exception as e:
                errors.append(u'Footing {}: {}'.format(get_id_value(host.Id), e))

        for host in floors:
            try:
                self._process_floor(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                errors.append(u'Floor {}: {}'.format(get_id_value(host.Id), e))

        created = len(created_rebars)

        tags_created = 0
        if created_rebars:
            view = self.doc.ActiveView
            # BUG FIX (2026-09-01) — reported live: tagging in a 3D view
            # requires that view to be LOCKED (a real Revit requirement,
            # nothing to do with this plugin's own code) — with no check
            # here, every single bar failed identically ("The 3D view
            # ownerDBViewId is not locked."), flooding the result log
            # with one near-duplicate line per bar (~30 for a modest
            # run) instead of ONE clear, actionable message. Skip
            # tagging outright with a single explanation instead of
            # attempting (and failing) it per bar.
            skip_reason = None
            try:
                if isinstance(view, DB.View3D) and not view.IsLocked:
                    skip_reason = (u'active 3D view "{}" is not locked — lock it '
                                    u'(View tab → Lock 3D View, or right-click the '
                                    u'view cube) or switch to a 2D/plan view before '
                                    u'running, then tag manually.').format(view.Name)
            except Exception:
                pass
            if skip_reason is not None:
                errors.append(u'Tagging skipped for all {} bar(s) — {}'.format(
                    len(created_rebars), skip_reason))
            else:
                try:
                    with revit.Transaction(u'NOSA — Tag Rebar'):
                        tags, tag_errors = rebar_detailing.create_rebar_tags(
                            self.doc, view, created_rebars)
                    tags_created = len(tags)
                    errors.extend(tag_errors)
                except Exception as e:
                    errors.append(u'Tagging failed: {}'.format(e))

        sections_created = 0
        if values['generate_sections'] and footings:
            sections_created = self._create_detail_sections(footings, errors)

        return created_rebars, {'created': created, 'tags': tags_created,
                                 'sections': sections_created, 'errors': errors}

    # ── Columns (Phase 3) ────────────────────────────────────────────────

    def ColumnDensify_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColDensify.IsEnabled = self.ChkColDensify.IsChecked == True
        self._update_column_preview()

    def ColumnCrossties_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColCrossties.IsEnabled = self.ChkColCrossties.IsChecked == True
        self._update_column_preview()

    def ColFoundationStarters_Click(self, sender, args):
        # PHASE F7.18 (2026-09-02) — no preview support yet (scope
        # disclosed to the user: this feature's own geometry depends on
        # a live foundation-detection query, not the illustrative-only
        # rebar_preview.py this window's other panels use) — just
        # enables/disables the length fields, matching every other
        # optional-panel checkbox's own convention.
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelColFoundationStarters.IsEnabled = self.ChkColFoundationStarters.IsChecked == True

    def ColumnPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_column_preview()

    def _update_column_preview(self):
        columns = self._selected_columns()
        col_host = columns[0] if columns else None

        # PHASE 3.5.3 item 4 — cover from the live selected column's
        # own native Rebar Cover, matching real generation exactly
        # (see _process_column) instead of a typed UI value.
        cover = self._preview_cover_mm(col_host, u'Exterior', u'column')
        try:
            bar_dia = float(self.TxtColBarDia.Text)
            bar_count = float(self.TxtColBarCount.Text)
            link_dia = float(self.TxtColLinkDia.Text)
        except (TypeError, ValueError):
            return
        if cover <= 0 or bar_dia <= 0 or bar_count < 4 or link_dia <= 0:
            return

        # Representative section — falls back to a fixed illustrative
        # 400x300mm rectangle when no column is selected or its
        # geometry can't be read; otherwise uses the REAL selected
        # host's own shape/aspect-ratio/diameter (Phase 3.4 item 4), so
        # the preview never shows a misleading rectangle for a round
        # column or the wrong proportions for a real rectangular one.
        width_mm, depth_mm = 400.0, 300.0
        shape, diameter_mm = 'rect', None
        try:
            if col_host is not None:
                geom = column_rebar.detect_column_geometry(self.doc, col_host)
                if geom is not None:
                    shape = geom['shape']
                    if shape == 'circle':
                        diameter_mm = geom['diameter_mm']
                    else:
                        width_mm, depth_mm = geom['width_mm'], geom['depth_mm']
        except Exception:
            shape, diameter_mm = 'rect', None
            width_mm, depth_mm = 400.0, 300.0

        crossties = self.ChkColCrossties.IsChecked == True
        crosstie_layout = ('alternate' if self.CboCrosstieLayout.SelectedIndex == 1
                            else 'all')

        try:
            data = rebar_preview.compute_column_section_preview(
                width_mm, depth_mm, cover, bar_dia, int(bar_count), link_dia,
                shape=shape, diameter_mm=diameter_mm,
                include_crossties=crossties, crosstie_layout=crosstie_layout)
        except ValueError:
            return

        self._draw_column_preview(data)
        self._update_column_adopted_solution_label(cover, bar_dia, int(bar_count), link_dia)
        self._update_column_elevation_preview()

    def _update_column_elevation_preview(self):
        columns = self._selected_columns()
        col_host = columns[0] if columns else None

        # PHASE 3.5.3 item 4 — same live-host native cover as the plan
        # preview (_update_column_preview) — see that method's note.
        cover = self._preview_cover_mm(col_host, u'Exterior', u'column')
        try:
            bar_dia = float(self.TxtColBarDia.Text)
            bar_count = float(self.TxtColBarCount.Text)
            link_dia = float(self.TxtColLinkDia.Text)
            normal_spacing = float(self.TxtColLinkSpacing.Text)
        except (TypeError, ValueError):
            return
        if cover <= 0 or bar_dia <= 0 or bar_count < 4 or link_dia <= 0 or normal_spacing <= 0:
            return

        densify = self.ChkColDensify.IsChecked == True
        dense_spacing = normal_spacing
        if densify:
            try:
                dense_spacing = float(self.TxtColDenseSpacing.Text)
            except (TypeError, ValueError):
                return
            if dense_spacing <= 0:
                return

        starter_bars = self.ChkColStarterBars.IsChecked == True
        cranked_laps = self.ChkColCrankedLaps.IsChecked == True
        crossties = self.ChkColCrossties.IsChecked == True

        # Same illustrative section as the plan preview, plus a
        # representative column height — this module has no real
        # host height/width available at preview time UNLESS a real
        # column is currently selected, in which case its own axis/
        # floor intersections/real cross-section width are used so the
        # preview reflects the ACTUAL multi-story splits/starters/
        # aspect ratio that will be generated (Phase 3.2 item 5 /
        # Phase 3.4 item 4) — best-effort only, silently falling back
        # to the plain illustrative case for any failure (nothing
        # selected, a non-rectangular host, etc.), matching this
        # method's existing defensive convention.
        width_mm, height_mm = 400.0, 3000.0
        floor_splits_mm = None
        floor_bands_mm = None
        preview_crank_offset_mm = None
        try:
            if col_host is not None:
                host = col_host
                axis = column_rebar.get_column_axis(host)
                height_mm = axis.Length * 304.8
                geom = column_rebar.detect_column_geometry(self.doc, host)
                if geom is not None:
                    width_mm = geom['diameter_mm'] if geom['shape'] == 'circle' else geom['width_mm']
                floor_entries = column_rebar.find_floor_split_elevations_ft(self.doc, axis)
                base_z_ft = axis.GetEndPoint(0).Z
                floor_splits_mm = [(e['top_ft'] - base_z_ft) * 304.8 for e in floor_entries]
                floor_bands_mm = [((e['bottom_ft'] - base_z_ft) * 304.8,
                                    (e['top_ft'] - base_z_ft) * 304.8) for e in floor_entries]
                if cranked_laps:
                    # A REAL, representative crank offset (Phase 3.3):
                    # resolved against whatever column is actually
                    # found above the LAST split (or this column's own
                    # top, if none) — the same detection
                    # build_column_reinforcement itself uses, not the
                    # old fixed-heuristic default. Uses the 'v' edge as
                    # representative (the elevation preview shows one
                    # face, not all 4).
                    engine = re_engine
                    cover_mgr = engine.CoverGeometryManager(self.doc, host)
                    u_pos, u_neg, v_pos, v_neg, u_dir, v_dir = column_rebar._column_faces(
                        cover_mgr, axis.Direction)
                    bar_inset_mm = cover + link_dia + bar_dia / 2.0 +                         engine.link_corner_extra_inset_mm(bar_dia, link_dia)
                    bar_half_w_mm, bar_half_d_mm = column_rebar._cross_section_half_extents(
                        engine, axis, u_pos, u_neg, v_pos, v_neg, u_dir, v_dir, bar_inset_mm)
                    top_elevation_ft = floor_entries[-1]['top_ft'] if floor_entries else axis.GetEndPoint(1).Z
                    preview_crank_offset_mm = column_rebar.resolve_crank_offset_mm(
                        self.doc, host, axis, top_elevation_ft, 'v', engine, bar_inset_mm,
                        bar_half_w_mm, bar_half_d_mm)
        except Exception:
            floor_splits_mm = None
            floor_bands_mm = None
            height_mm = 3000.0
            preview_crank_offset_mm = None

        try:
            data = rebar_preview.compute_column_elevation_preview(
                width_mm, height_mm, cover, bar_dia, int(bar_count), link_dia,
                dense_spacing, normal_spacing, densify, starter_bars,
                floor_splits_mm=floor_splits_mm, use_cranked_laps=cranked_laps,
                crank_offset_mm=preview_crank_offset_mm,
                floor_bands_mm=floor_bands_mm, include_crossties=crossties)
        except ValueError:
            return

        self._draw_column_elevation_preview(data)

    def _draw_column_elevation_preview(self, data):
        canvas = self.ColumnElevationCanvas
        canvas.Children.Clear()

        section = data['section']
        w_mm = section['width_mm']
        h_mm = section['height_mm']
        starter_ext = data['starter_extension_mm']

        cw = canvas.Width
        ch = canvas.Height
        margin_x = 40.0
        margin_top = 16.0
        margin_bottom = 16.0
        total_h_mm = h_mm + starter_ext
        scale = min((cw - 2 * margin_x) / w_mm, (ch - margin_top - margin_bottom) / total_h_mm)
        off_x = cw / 2.0
        off_y = ch - margin_bottom

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        # Column outline (base to head, excluding starter projection)
        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 1.5
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        # Floor-split reference lines (Phase 3.2 item 5) — dashed,
        # drawn full-width, one per intermediate storey join detected
        # on the currently selected column's own axis.
        for split_mm in data.get('floor_splits_mm', []):
            line = SWS.Line()
            line.X1 = sx(-w_mm / 2.0 - 6.0)
            line.X2 = sx(w_mm / 2.0 + 6.0)
            line.Y1 = sy(split_mm)
            line.Y2 = sy(split_mm)
            line.Stroke = _PREVIEW_SECTION_STROKE
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([4.0, 3.0])
            canvas.Children.Add(line)

        # Vertical bar segments — one or more per bar position (a
        # straight run per storey, plus a straight or cranked starter
        # at each split/the head, if any — see
        # rebar_preview.compute_column_elevation_preview).
        for bar in data['bars']:
            line = SWS.Line()
            line.X1 = sx(bar['x0_mm'])
            line.X2 = sx(bar['x1_mm'])
            line.Y1 = sy(bar['y0_mm'])
            line.Y2 = sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, bar['diameter_mm'] * scale)
            canvas.Children.Add(line)

        # Horizontal link/tie lines, illustrating densification at
        # nodes — excludes any Z inside a detected floor's own
        # thickness (Phase 3.4 item 2), matching the real generator.
        for link in data['links']:
            line = SWS.Line()
            line.X1 = sx(-link['half_w_mm'])
            line.X2 = sx(link['half_w_mm'])
            line.Y1 = sy(link['y_mm'])
            line.Y2 = sy(link['y_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.5
            canvas.Children.Add(line)

        # Interior crosstie lines (Phase 3.4 item 5) — shorter, dashed,
        # crossing only the core.
        for tie in data.get('crossties', []):
            line = SWS.Line()
            line.X1 = sx(-tie['half_w_mm'])
            line.X2 = sx(tie['half_w_mm'])
            line.Y1 = sy(tie['y_mm'])
            line.Y2 = sy(tie['y_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([3.0, 2.0])
            canvas.Children.Add(line)

    def _draw_column_preview(self, data):
        canvas = self.ColumnPreviewCanvas
        canvas.Children.Clear()

        section = data['section']
        w_mm = section['width_mm']
        h_mm = section['height_mm']

        cw = canvas.Width
        ch = canvas.Height
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        off_x = cw / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        # Concrete section outline — a circle for a round column
        # (Phase 3.4 item 4), a rectangle at its REAL aspect ratio
        # otherwise.
        is_circle = section.get('shape') == 'circle'
        outline = SWS.Ellipse() if is_circle else SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 1.5
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm / 2.0))
        canvas.Children.Add(outline)

        # Stirrup (Link/Tie) perimeter outline, cover-inset
        stirrup = data['stirrup']
        st_w = stirrup['half_w_mm'] * 2.0 * scale
        st_d = stirrup['half_d_mm'] * 2.0 * scale
        st_shape = SWS.Ellipse() if is_circle else SWS.Rectangle()
        st_shape.Width = st_w
        st_shape.Height = st_d
        st_shape.Stroke = _PREVIEW_BAR_FILL
        st_shape.StrokeThickness = 1.5
        st_shape.Fill = SWM.Brushes.Transparent
        SWC.Canvas.SetLeft(st_shape, sx(-stirrup['half_w_mm']))
        SWC.Canvas.SetTop(st_shape, sy(stirrup['half_d_mm']))
        canvas.Children.Add(st_shape)

        # Vertical bar dots
        for bar in data['bars']:
            dot_d = max(4.0, bar['diameter_mm'] * scale)
            dot = SWS.Ellipse()
            dot.Width = dot_d
            dot.Height = dot_d
            dot.Fill = _PREVIEW_BAR_FILL
            SWC.Canvas.SetLeft(dot, sx(bar['x_mm']) - dot_d / 2.0)
            SWC.Canvas.SetTop(dot, sy(bar['y_mm']) - dot_d / 2.0)
            canvas.Children.Add(dot)

        # PHASE 3.5.1 item 4 — interior crosstie lines, plan view: each
        # line connects an intermediate bar to its direct mirror across
        # the section, the exact same (x1,y1)-(x2,y2) pairing
        # column_rebar.build_crosstie_sets computes for real creation
        # (see compute_column_section_preview/_crosstie_lines_preview).
        for tie in data.get('crossties', []):
            line = SWS.Line()
            line.X1 = sx(tie['x1_mm'])
            line.Y1 = sy(tie['y1_mm'])
            line.X2 = sx(tie['x2_mm'])
            line.Y2 = sy(tie['y2_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.0
            line.StrokeDashArray = SWM.DoubleCollection([3.0, 2.0])
            canvas.Children.Add(line)

    def _update_column_adopted_solution_label(self, cover, bar_dia, bar_count, link_dia):
        text = (u'Adopted Solution — {} x Ø{:.0f}mm verticals, Ø{:.0f}mm links, '
                u'{:.0f}mm cover').format(bar_count, bar_dia, link_dia, cover)
        self.TxtColumnAdoptedSolution.Text = text

    def _selected_columns(self):
        ids = self.uidoc.Selection.GetElementIds()
        columns = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_StructuralColumns'):
                columns.append(elem)
        return columns

    def _selected_beams(self):
        ids = self.uidoc.Selection.GetElementIds()
        beams = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_StructuralFraming'):
                beams.append(elem)
        return beams

    def _selected_walls(self):
        ids = self.uidoc.Selection.GetElementIds()
        walls = []
        for eid in ids:
            elem = self.doc.GetElement(eid)
            if elem is None or elem.Category is None:
                continue
            if get_id_value(elem.Category.Id) == _cat_id('OST_Walls'):
                walls.append(elem)
        return walls

    def _read_column_inputs(self):
        errors = []
        values = {}

        # PHASE 3.5.3 item 4 — cover is no longer read here: it's
        # resolved per-host from native Rebar Cover in _process_column.
        values['bar_dia'] = self._read_number(self.TxtColBarDia.Text, u'Vertical bar diameter', errors)
        try:
            values['bar_count'] = int(float(self.TxtColBarCount.Text))
            if values['bar_count'] < 4:
                errors.append(u'"Quantity" must be at least 4.')
        except (TypeError, ValueError):
            errors.append(u'"Quantity" must be a number.')
            values['bar_count'] = None
        values['link_dia'] = self._read_number(self.TxtColLinkDia.Text, u'Link diameter', errors)
        values['link_spacing'] = self._read_number(
            self.TxtColLinkSpacing.Text, u'Link centre spacing', errors)
        values['densify'] = self.ChkColDensify.IsChecked == True
        if values['densify']:
            values['dense_spacing'] = self._read_number(
                self.TxtColDenseSpacing.Text, u'Densified spacing at nodes', errors)
        values['starter_bars'] = self.ChkColStarterBars.IsChecked == True
        values['cranked_laps'] = self.ChkColCrankedLaps.IsChecked == True
        values['crossties'] = self.ChkColCrossties.IsChecked == True
        values['crosstie_layout'] = ('alternate' if self.CboCrosstieLayout.SelectedIndex == 1
                                      else 'all')

        # PHASE F7.18 (2026-09-02, explicit request) — L-shaped starters
        # into whatever foundation (isolated/strip footing or floor/mat
        # slab) is detected below the column, distinct from starter_bars
        # above (which extends the column's OWN top, for future storeys).
        values['foundation_starters'] = self.ChkColFoundationStarters.IsChecked == True
        if values['foundation_starters']:
            values['foundation_anchor_mm'] = self._read_number(
                self.TxtColFoundationAnchor.Text, u'Foundation starter anchor length', errors)
            values['foundation_splice_mm'] = self._read_number(
                self.TxtColFoundationSplice.Text, u'Foundation starter splice length', errors)

        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def RunColumnReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_column_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'columns', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_column_result(self, columns, summary):
        lines = [
            u'{} column(s) processed.'.format(len(columns)),
            u'{} Rebar element(s) created (sets count as one each).'.format(summary['created']),
        ]
        if summary['errors']:
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — same fix as _show_reinforcement_result.
            lines.extend(summary['errors'])
        self.TxtColumnResult.Text = u'\n'.join(lines)

    def _process_column(self, host, values, wrapper, bar_types, errors, created_rebars):
        """
        PHASE 3.2 — vertical bars are now Rebar SETS, one per column
        face per storey segment (SetLayoutAsFixedNumber — see
        column_rebar.build_column_reinforcement's own docstring for why
        this is now a Set, and for the multi-story splitting/cranked-lap
        behaviour); the rare face reduced to a single bar position
        (e.g. a V-edge on a small column) stays an individual element,
        since a Set has nothing to propagate for a count of 1.
        Links/ties remain Rebar Sets (1 zone, or 3 if
        densify_at_nodes, now split further wherever they'd otherwise
        run through a detected floor — Phase 3.4 item 2), the same
        create_rebar_set mechanism footing_rebar.build_side_rebar_set
        already proved live for a vertically-propagated closed
        rectangle. Interior crossties (Phase 3.5 item 2), if
        requested, are INDIVIDUAL bars (not Sets) created via
        create_from_curves with start_hook/end_hook baked in at
        creation — Rebar.SetHookTypeId post-creation on a Set was
        confirmed to crash live ("hookTypeId is not valid") since a
        Set-propagated line has no hook-aware RebarShape.
        """
        # PHASE 3.5.3 item 4 — cover read from THIS host's own native
        # Rebar Cover ('Exterior' face — a column's cover is uniform
        # across all 4 side faces in this plugin's model), not a UI
        # text field.
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Exterior', self._standard_default_cover_mm(u'column'))
        reinforcement = column_rebar.build_column_reinforcement(
            self.doc, host,
            cover_mm=cover_mm,
            bar_diameter_mm=values['bar_dia'],
            bar_count=values['bar_count'],
            stirrup_diameter_mm=values['link_dia'],
            dense_spacing_mm=values.get('dense_spacing', values['link_spacing']),
            normal_spacing_mm=values['link_spacing'],
            densify_at_nodes=values['densify'],
            include_starter_bars=values['starter_bars'],
            use_cranked_laps=values['cranked_laps'],
            include_crossties=values['crossties'],
            crosstie_layout=values['crosstie_layout'],
            std=getattr(self, 'ra_standard', None))

        for w in reinforcement.get('warnings', []):
            errors.append(u'Column {}: {}'.format(get_id_value(host.Id), w))

        # DIAGNOSTIC HARDENING (2026-09-01) — a circular column was
        # reported creating ZERO rebar with NO error at all, which
        # should be impossible if a caught exception was the cause (see
        # this file's outer try/except in _run_column_reinforcement).
        # The remaining explanation is build_column_reinforcement
        # itself returning normally with every list empty — nothing to
        # create, nothing to fail, hence silence. Surface that
        # explicitly so it is never silent again.
        if not any(reinforcement.get(k) for k in (
                'vertical_bars', 'vertical_bar_sets', 'stirrup_sets',
                'interior_stirrup_sets', 'crosstie_sets')):
            errors.append(
                u'Column {}: build_column_reinforcement returned with NO curves '
                u'at all (no exception, no warnings) — nothing to create. This '
                u'points at generate_column_stirrup_zones/_subtract_floor_bands '
                u'or build_story_segment_chains producing empty output for this '
                u'host\'s specific geometry (e.g. a multi-storey split); please '
                u'report this exact column/model to investigate further.'.format(
                    get_id_value(host.Id)))

        bar_type_vert = bar_types.get(values['bar_dia'])
        first_vertical = len(created_rebars)
        if bar_type_vert is not None:
            for vs in reinforcement['vertical_bar_sets']:
                rebar = wrapper.create_rebar_set_fixed_number(
                    host, vs['curves'], bar_type_vert, vs['count'], vs['array_length_mm'],
                    normal=vs['normal'],
                    transaction_name=u'NOSA — Create Column Vertical Bars')
                if rebar is None:
                    errors.append(u'Column {}: vertical bars (set) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'vertical')
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Column {}: vertical bars (set) — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
            for vb in reinforcement['vertical_bars']:
                rebar = wrapper.create_from_curves(
                    host, vb['curves'], bar_type_vert, normal=vb['normal'],
                    transaction_name=u'NOSA — Create Column Vertical Bar')
                if rebar is None:
                    errors.append(u'Column {}: vertical bar — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'vertical')
                    created_rebars.append(rebar)

        vertical_rebars = created_rebars[first_vertical:]

        bar_type_link = bar_types.get(values['link_dia'])
        if bar_type_link is not None:
            for s in reinforcement['stirrup_sets']:
                style = DBS.RebarStyle.StirrupTie if s.get('style') == 'StirrupTie' else None
                rebar = wrapper.create_rebar_set(
                    host, s['curves'], bar_type_link, s['spacing_mm'], s['array_length_mm'],
                    normal=s['normal'], style=style,
                    transaction_name=u'NOSA — Create Column Links')
                if rebar is None:
                    errors.append(u'Column {}: links (set) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'stirrup')
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Column {}: links (set) — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))

            # PHASE 3.5.8 item 2 — normative interior stirrup loops
            # (collapsed crossties) use the SAME Set mechanism as the
            # main stirrups above, not create_from_curves.
            for iss in reinforcement.get('interior_stirrup_sets', []):
                style = DBS.RebarStyle.StirrupTie if iss.get('style') == 'StirrupTie' else None
                rebar = wrapper.create_rebar_set(
                    host, iss['curves'], bar_type_link, iss['spacing_mm'], iss['array_length_mm'],
                    normal=iss['normal'], style=style,
                    transaction_name=u'NOSA — Create Column Interior Stirrup')
                if rebar is None:
                    errors.append(u'Column {}: interior stirrup (set) — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'interior_stirrup')
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Column {}: interior stirrup (set) — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))

            if reinforcement['crosstie_sets']:
                hook_135 = re_engine.get_hook_type_by_angle(self.doc, 135.0)
                hook_90 = re_engine.get_hook_type_by_angle(self.doc, 90.0)
                if hook_135 is None and hook_90 is None:
                    errors.append(u'Column {}: crossties — no 135°/90° RebarHookType '
                                  u'found in this project; crossties will be created '
                                  u'WITHOUT hooks (not normative anchorage).'.format(
                                      get_id_value(host.Id)))
                # Hooks are baked in AT creation via create_from_curves
                # (start_hook/end_hook) — NOT applied post-creation via
                # Rebar.SetHookTypeId. That combination crashed live
                # ("hookTypeId is not valid"): a Set-propagated bar has
                # no hook-aware RebarShape for SetHookTypeId to target.
                # Crossties are therefore individual bars, not Sets —
                # see build_crosstie_sets's docstring.
                for ct in reinforcement['crosstie_sets']:
                    rebar = wrapper.create_from_curves(
                        host, [ct['curve']], bar_type_link,
                        start_hook=hook_135, end_hook=hook_90,
                        normal=ct['normal'],
                        transaction_name=u'NOSA — Create Column Crossties')
                    if rebar is None:
                        errors.append(u'Column {}: crosstie — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                        continue
                    self._stamp_layer(rebar, u'crosstie')
                    created_rebars.append(rebar)

        # PHASE F7.18 (2026-09-02, explicit request — "Starter bars con
        # forma de L en columnas y muros... unidas a la cimentación") —
        # a representative 4-corner starter cage (n_u=n_v=2, matching
        # footing_rebar's own Dowels default of 4) reaching down into
        # whatever foundation is detected below this column, distinct
        # from values['starter_bars'] above (the column's OWN top, for
        # future storeys — unrelated direction/purpose).
        if vertical_rebars and reinforcement.get('bar_inset_mm'):
            # T2.10b: links re-snap the verticals; pin them back to the design inset.
            try:
                with DB.Transaction(self.doc, u'NOSA — Pin Column Vertical Bars') as t:
                    t.Start()
                    for rebar in vertical_rebars:
                        re_engine.pin_rebar_to_host_faces(
                            self.doc, rebar, host, reinforcement['bar_inset_mm'])
                    t.Commit()
            except Exception as e:
                errors.append(u'Column {}: vertical bars left where Revit snapped them '
                              u'(could not pin to the faces: {}).'.format(get_id_value(host.Id), e))

        if values.get('foundation_starters') and bar_type_vert is not None and \
                re_engine.nosa_bars_in_footprint(self.doc, host, (u'dowel', u'foundation_starter')):
            errors.append(u'Column {}: foundation starters skipped — the footing below already '
                          u'has NOSA dowels (or starters) under this column.'.format(get_id_value(host.Id)))
        elif values.get('foundation_starters') and bar_type_vert is not None:
            points = re_engine.unique_plan_points(
                [p for r in vertical_rebars for p in re_engine.rebar_bar_plan_points(r)])
            starters = column_rebar.build_column_foundation_starters(
                self.doc, host, points, values['bar_dia'], values['bar_dia'],
                values['foundation_anchor_mm'], values['foundation_splice_mm'],
                foundation_cover_mm=cover_mm)
            hook_90 = re_engine.get_hook_type_by_angle(self.doc, 90.0)
            if hook_90 is None:
                errors.append(u'Column {}: foundation starters — no 90° RebarHookType '
                              u'found in this project; created WITHOUT hooks (not '
                              u'normative anchorage).'.format(get_id_value(host.Id)))
            self._create_foundation_starter_bars(
                wrapper, host, starters, bar_type_vert, hook_90, u'Column',
                errors, created_rebars)

    def _run_column_reinforcement(self, columns, values):
        """
        PHASE F1 — see _run_reinforcement's own docstring for why the
        TransactionGroup that used to wrap this loop moved up into
        rebar_batch.RebarBatch.run instead (Revit doesn't support a
        nested/concurrent TransactionGroup, and the outer one now also
        needs to cover the provenance-stamping pass). Geometry
        generation itself is unchanged.

        Returns:
            (created_rebars, summary) — see _run_reinforcement's own
            docstring for the same PHASE F1 return-shape change.
        """
        errors = []
        diameters = {values['bar_dia'], values['link_dia']}
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []

        for host in columns:
            try:
                self._process_column(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                # DIAGNOSTIC HARDENING (2026-09-01) — a circular column
                # was reported creating ZERO rebar with NO error message
                # at all, which should be impossible if an exception is
                # what stopped it (this except already appends one).
                # Capture the full traceback so a genuine silent-failure
                # report always has an exact line to act on next time —
                # a bare `{}`.format(e) can render as an empty string
                # for some exception types, which would itself look like
                # "no error" even though this branch DID run.
                import traceback
                detail = u'{}'.format(e) or u'(empty exception message)'
                try:
                    detail = u'{}\n{}'.format(detail, traceback.format_exc())
                except Exception:
                    pass
                errors.append(u'Column {}: {}'.format(get_id_value(host.Id), detail))

        return created_rebars, {'created': len(created_rebars), 'errors': errors}

    # ── Beams (Phase F7) ─────────────────────────────────────────────────

    def _read_beam_inputs(self):
        errors = []
        values = {}
        values['bar_dia'] = self._read_number(self.TxtBeamBarDia.Text, u'Bar diameter', errors)
        try:
            values['n_top'] = int(float(self.TxtBeamTopCount.Text))
            if values['n_top'] < 0:
                errors.append(u'"Top bars" must be zero or positive.')
        except (TypeError, ValueError):
            errors.append(u'"Top bars" must be a number.')
            values['n_top'] = None
        try:
            values['n_bottom'] = int(float(self.TxtBeamBottomCount.Text))
            if values['n_bottom'] < 0:
                errors.append(u'"Bottom bars" must be zero or positive.')
        except (TypeError, ValueError):
            errors.append(u'"Bottom bars" must be a number.')
            values['n_bottom'] = None
        values['stirrup_dia'] = self._read_number(
            self.TxtBeamStirrupDia.Text, u'Stirrup diameter', errors)
        values['stirrup_spacing'] = self._read_number(
            self.TxtBeamStirrupSpacing.Text, u'Stirrup spacing', errors)
        values['end_offset'] = self._read_number(
            self.TxtBeamEndOffset.Text, u'End offset', errors)
        values['stock_length'] = self._read_number(
            self.TxtBeamStockLength.Text, u'Max stock length', errors)
        if values.get('stock_length') is not None and values['stock_length'] < 1000.0:
            errors.append(u'"Max stock length" must be at least 1000 mm.')
        values['densify_ends'] = self.ChkBeamDensify.IsChecked == True
        if values['densify_ends']:
            values['dense_spacing'] = self._read_number(
                self.TxtBeamDenseSpacing.Text, u'Dense spacing', errors)
            # 0 = auto (2 × beam height); allow zero without failing validation
            try:
                conf = float(self.TxtBeamConfineLength.Text)
            except (TypeError, ValueError):
                errors.append(u'"Confine length" must be a number (0 = auto).')
                conf = None
            if conf is not None and conf < 0:
                errors.append(u'"Confine length" cannot be negative.')
                conf = None
            values['confine_length'] = conf if (conf and conf > 0) else None
        if values.get('n_top') == 0 and values.get('n_bottom') == 0:
            errors.append(u'At least one top or bottom bar is required.')
        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def BeamDensify_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelBeamDensify.IsEnabled = self.ChkBeamDensify.IsChecked == True
        self._update_beam_preview()

    def BeamPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_beam_preview()

    def _update_beam_preview(self):
        try:
            canvas = self.BeamPreviewCanvas
        except Exception:
            return
        try:
            bar_dia = float(self.TxtBeamBarDia.Text)
            n_top = int(float(self.TxtBeamTopCount.Text))
            n_bottom = int(float(self.TxtBeamBottomCount.Text))
            st_dia = float(self.TxtBeamStirrupDia.Text)
        except (TypeError, ValueError):
            return
        beams = self._selected_beams()
        beam_host = beams[0] if beams else None
        cover = self._preview_cover_mm(beam_host, u'Other', u'beam') if beam_host else \
            self._standard_default_cover_mm(u'beam')
        width_mm, height_mm = 300.0, 500.0
        if beam_host is not None:
            try:
                width_mm, height_mm = beam_rebar.get_beam_section_mm(
                    self.doc, beam_host, cover, bar_dia)
            except Exception:
                pass
        try:
            data = rebar_preview.compute_beam_section_preview(
                width_mm, height_mm, cover, bar_dia, n_top, n_bottom, st_dia)
        except Exception:
            return
        self._draw_simple_section_preview(canvas, data, draw_stirrup=True)
        self._update_beam_elevation_preview()

    def _update_beam_elevation_preview(self):
        """
        PHASE 2.6 (2026-09-02, explicit live request — "sería
        interesante ver un alzado de la viga") — companion elevation
        (side view) beside the existing section preview, mirroring the
        Columns tab's own Section+Elevation pair. Silently skipped
        (never raises to the caller) if the elevation canvas doesn't
        exist yet in ui.xaml, or if any input is invalid/mid-typing —
        same defensive convention as every other _update_*_preview.
        """
        try:
            canvas = self.BeamElevationCanvas
        except Exception:
            return
        try:
            bar_dia = float(self.TxtBeamBarDia.Text)
            st_dia = float(self.TxtBeamStirrupDia.Text)
            st_spacing = float(self.TxtBeamStirrupSpacing.Text)
            end_offset = float(self.TxtBeamEndOffset.Text)
        except (TypeError, ValueError):
            return

        densify = self.ChkBeamDensify.IsChecked == True
        dense_spacing = confine_length = None
        if densify:
            try:
                dense_spacing = float(self.TxtBeamDenseSpacing.Text)
                confine_txt = float(self.TxtBeamConfineLength.Text)
                confine_length = confine_txt if confine_txt > 0 else None
            except (TypeError, ValueError):
                return
            if dense_spacing <= 0:
                return

        beams = self._selected_beams()
        beam_host = beams[0] if beams else None
        cover = self._preview_cover_mm(beam_host, u'Other', u'beam') if beam_host else \
            self._standard_default_cover_mm(u'beam')
        length_mm, height_mm = 6000.0, 500.0
        if beam_host is not None:
            try:
                _, height_mm = beam_rebar.get_beam_section_mm(self.doc, beam_host, cover, bar_dia)
            except Exception:
                pass
            try:
                length_mm = beam_rebar.get_beam_axis(beam_host).Length * 304.8
            except Exception:
                pass

        try:
            data = rebar_preview.compute_beam_elevation_preview(
                length_mm, height_mm, cover, bar_dia, bar_dia, st_dia, st_spacing,
                end_offset_mm=end_offset, densify_ends=densify,
                dense_spacing_mm=dense_spacing, confine_length_mm=confine_length)
        except Exception:
            return
        self._draw_beam_elevation_preview(canvas, data)

    def _draw_beam_elevation_preview(self, canvas, data):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 6000.0)
        h_mm = float(section.get('height_mm') or 500.0)
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        # Centred exactly like _draw_column_elevation_preview — this
        # function's own coordinate system spans x in [0, w_mm], so
        # centring means offsetting by however much blank canvas space
        # the SCALED beam doesn't fill, split evenly on both sides
        # (never a fixed small margin — see _draw_wall_elevation_preview's
        # own BUG FIX note for the "stuck flush-left" failure mode this
        # avoids from the start).
        off_x = (cw - w_mm * scale) / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - (y_mm - h_mm / 2.0) * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(0.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        for st in data.get('stirrups', []):
            line = SWS.Line()
            line.X1 = line.X2 = sx(st['x_mm'])
            line.Y1 = sy(st['y0_mm'])
            line.Y2 = sy(st['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.0, float(st.get('diameter_mm') or 8.0) * scale * 0.6)
            canvas.Children.Add(line)

        for bar in data.get('bars', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(bar['x0_mm']), sy(bar['y0_mm'])
            line.X2, line.Y2 = sx(bar['x1_mm']), sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, float(bar.get('diameter_mm') or 16.0) * scale)
            canvas.Children.Add(line)

    def _update_wall_preview(self):
        cover = self._standard_default_cover_mm(u'wall')
        walls = self._selected_walls()
        wall_host = walls[0] if walls else None
        thickness_mm = 250.0
        length_mm, height_mm = 6000.0, 3000.0
        if wall_host is not None:
            try:
                cover = re_engine.get_native_cover_mm(
                    self.doc, wall_host, u'Exterior', cover)
            except Exception:
                pass
            try:
                length_mm, height_mm = wall_rebar.get_wall_elevation_mm(wall_host)
            except Exception:
                pass
            try:
                thickness_mm = wall_host.Width * 304.8
            except Exception:
                pass

        try:
            vert_dia = float(self.TxtWallVertDia.Text)
            vert_sp = float(self.TxtWallVertSpacing.Text)
            horiz_dia = float(self.TxtWallHorizDia.Text)
            horiz_sp = float(self.TxtWallHorizSpacing.Text)
        except (TypeError, ValueError):
            return
        both_faces = self.ChkWallBothFaces.IsChecked == True

        try:
            elevation_canvas = self.WallPreviewCanvas
        except Exception:
            elevation_canvas = None
        if elevation_canvas is not None:
            include_starters = self.ChkWallStarters.IsChecked == True
            starter_length = None
            if include_starters:
                try:
                    starter_length = float(self.TxtWallStarterLength.Text)
                    if starter_length <= 0:
                        starter_length = None  # 0 = auto, matches build_wall_reinforcement
                except (TypeError, ValueError):
                    starter_length = None
            try:
                data = rebar_preview.compute_wall_elevation_preview(
                    length_mm=length_mm, height_mm=height_mm, cover_mm=cover,
                    vert_dia_mm=vert_dia, vert_spacing_mm=vert_sp,
                    horiz_spacing_mm=horiz_sp, horiz_dia_mm=horiz_dia,
                    both_faces=both_faces,
                    include_top_ubars=self.ChkWallEndUBars.IsChecked == True,
                    include_end_ubars=self.ChkWallEndUBars.IsChecked == True,
                    include_starters=include_starters, starter_length_mm=starter_length)
            except Exception:
                pass
            else:
                self._draw_wall_elevation_preview(elevation_canvas, data)

        # PHASE 2.6 (2026-09-02, explicit live request — "sería
        # conveniente que se viese una sección, el nombre... dice
        # Section Preview cuando es un alzado", then "la sección no se
        # ve correctamente, necesitaríamos una sección bien hecha") —
        # genuine cross-section (a VERTICAL cut PERPENDICULAR to the
        # wall's own length, through its thickness), alongside the
        # elevation above. Reuses _draw_simple_section_preview (now
        # extended with a 'bar_lines' renderer for the vertical bars —
        # see that method's own note).
        try:
            section_canvas = self.WallSectionCanvas
        except Exception:
            return
        include_ties = self.ChkWallTies.IsChecked == True
        tie_spacing = None
        if include_ties:
            try:
                tie_spacing = float(self.TxtWallTieSpacing.Text)
                if tie_spacing <= 0:
                    include_ties = False
            except (TypeError, ValueError):
                include_ties = False
        # A representative slice, not the wall's real height (same role
        # length_mm/height_mm play in compute_beam_elevation_preview) —
        # tall enough relative to a typical thickness to read clearly as
        # a section rather than a square blob, and to show 2-3 real
        # horizontal-bar row crossings at the user's own spacing.
        section_height_mm = max(900.0, thickness_mm * 3.0)
        try:
            section_data = rebar_preview.compute_wall_section_preview(
                thickness_mm, section_height_mm, cover, vert_dia, horiz_dia, horiz_sp,
                both_faces=both_faces,
                include_ties=include_ties, tie_spacing_mm=tie_spacing,
                include_ubars=self.ChkWallEndUBars.IsChecked == True)
        except Exception:
            return
        self._draw_simple_section_preview(section_canvas, section_data)

    def _draw_simple_section_preview(self, canvas, data, draw_stirrup=False):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 300.0)
        h_mm = float(section.get('height_mm') or 500.0)
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin = 16.0
        scale = min((cw - 2 * margin) / w_mm, (ch - 2 * margin) / h_mm)
        off_x = cw / 2.0
        off_y = ch / 2.0

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(-w_mm / 2.0))
        SWC.Canvas.SetTop(outline, sy(h_mm / 2.0))
        canvas.Children.Add(outline)

        if draw_stirrup and data.get('stirrup'):
            st = data['stirrup']
            hw, hh = st['half_w_mm'], st['half_h_mm']
            rect = SWS.Rectangle()
            rect.Width = 2.0 * hw * scale
            rect.Height = 2.0 * hh * scale
            rect.Stroke = _PREVIEW_BAR_FILL
            rect.StrokeThickness = 1.5
            rect.Fill = None
            try:
                rect.Fill = SWM.Brushes.Transparent
            except Exception:
                pass
            SWC.Canvas.SetLeft(rect, sx(-hw))
            SWC.Canvas.SetTop(rect, sy(hh))
            canvas.Children.Add(rect)

        for bar in data.get('bars', []):
            d = max(float(bar.get('diameter_mm') or 12.0), 6.0)
            r = (d * scale) / 2.0
            dot = SWS.Ellipse()
            dot.Width = r * 2.0
            dot.Height = r * 2.0
            dot.Fill = _PREVIEW_BAR_FILL
            SWC.Canvas.SetLeft(dot, sx(bar['x_mm']) - r)
            SWC.Canvas.SetTop(dot, sy(bar['y_mm']) - r)
            canvas.Children.Add(dot)

        # PHASE 2.6 (2026-09-02) — generic diameter-scaled bar LINE
        # segments, added for the rewritten wall section preview's
        # vertical bars (one continuous line per face) — a "lines" list
        # already existed for footings' B2/T2 (fixed-y, x0..x1 only);
        # this is the general x0/y0/x1/y1 shape any future caller can
        # reuse for a bar that isn't axis-locked to a single row.
        for bl in data.get('bar_lines', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(bl['x0_mm']), sy(bl['y0_mm'])
            line.X2, line.Y2 = sx(bl['x1_mm']), sy(bl['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(2.0, float(bl.get('diameter_mm') or 12.0) * scale)
            canvas.Children.Add(line)

        for tie in data.get('ties', []):
            line = SWS.Line()
            line.X1, line.Y1 = sx(tie['x0_mm']), sy(tie['y0_mm'])
            line.X2, line.Y2 = sx(tie['x1_mm']), sy(tie['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = 1.5
            canvas.Children.Add(line)

        for ub in data.get('ubars', []):
            pts = ub.get('points') or []
            for i in range(len(pts) - 1):
                line = SWS.Line()
                line.X1, line.Y1 = sx(pts[i][0]), sy(pts[i][1])
                line.X2, line.Y2 = sx(pts[i + 1][0]), sy(pts[i + 1][1])
                line.Stroke = _PREVIEW_UBAR_WEAVE_STROKE
                line.StrokeThickness = 1.5
                canvas.Children.Add(line)

    def _draw_wall_elevation_preview(self, canvas, data):
        canvas.Children.Clear()
        section = data.get('section') or {}
        w_mm = float(section.get('width_mm') or 6000.0)
        h_mm = float(section.get('height_mm') or 3000.0)
        # BUG FIX (2026-09-02, round 2, live report — "los starter bars
        # no se ven") — same starter_extension_mm pattern _draw_column_
        # elevation_preview already uses: the scale/offset must account
        # for the starter's own extension BELOW y=0, or those bar
        # segments get drawn off the bottom of the canvas / squeezed the
        # scale as if they didn't exist.
        starter_ext = float(data.get('starter_extension_mm') or 0.0)
        total_h_mm = h_mm + starter_ext
        cw = canvas.Width or 700.0
        ch = canvas.Height or 220.0
        margin_x = 24.0
        margin_y = 16.0
        scale = min((cw - 2 * margin_x) / w_mm, (ch - 2 * margin_y) / total_h_mm)
        # BUG FIX (2026-09-02, live report — "la vista de los walls
        # preview no está centrada") — off_x used to be the fixed left
        # MARGIN itself, so the wall was always drawn flush against the
        # left edge with all the leftover canvas width (whenever the
        # wall's own scaled length was shorter than the canvas, e.g. a
        # short wall or a wide window) going unused on the right. Centre
        # the ACTUAL scaled wall width within the canvas instead — same
        # fix shape as _draw_beam_elevation_preview's own centring.
        off_x = (cw - w_mm * scale) / 2.0
        # y=0 (the wall's own base) is shifted UP from the bottom margin
        # by however much room the starter extension needs below it, so
        # the starter's own bottom (y=-starter_ext) still lands exactly
        # at the bottom margin instead of running off the canvas.
        off_y = ch - margin_y - starter_ext * scale

        def sx(x_mm):
            return off_x + x_mm * scale

        def sy(y_mm):
            return off_y - y_mm * scale

        outline = SWS.Rectangle()
        outline.Width = w_mm * scale
        outline.Height = h_mm * scale
        outline.Stroke = _PREVIEW_SECTION_STROKE
        outline.StrokeThickness = 2.0
        outline.Fill = _PREVIEW_SECTION_FILL
        SWC.Canvas.SetLeft(outline, sx(0.0))
        SWC.Canvas.SetTop(outline, sy(h_mm))
        canvas.Children.Add(outline)

        for bar in data.get('bars', []):
            line = SWS.Line()
            line.X1 = sx(bar['x0_mm'])
            line.X2 = sx(bar['x1_mm'])
            line.Y1 = sy(bar['y0_mm'])
            line.Y2 = sy(bar['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.5, float(bar.get('diameter_mm') or 12.0) * scale * 0.5)
            canvas.Children.Add(line)

        for hz in data.get('horizontals', []):
            line = SWS.Line()
            line.X1 = sx(hz['x0_mm'])
            line.X2 = sx(hz['x1_mm'])
            line.Y1 = sy(hz['y0_mm'])
            line.Y2 = sy(hz['y1_mm'])
            line.Stroke = _PREVIEW_BAR_FILL
            line.StrokeThickness = max(1.0, float(hz.get('diameter_mm') or 10.0) * scale * 0.4)
            canvas.Children.Add(line)

        for ub in data.get('ubars', []):
            pts = ub.get('points') or []
            stroke = _PREVIEW_UBAR_WEAVE_STROKE
            for i in range(len(pts) - 1):
                seg = SWS.Line()
                seg.X1, seg.Y1 = sx(pts[i][0]), sy(pts[i][1])
                seg.X2, seg.Y2 = sx(pts[i + 1][0]), sy(pts[i + 1][1])
                seg.Stroke = stroke
                seg.StrokeThickness = 1.5
                canvas.Children.Add(seg)

    def RunBeamReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_beam_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'beams', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_beam_result(self, beams, summary):
        lines = [
            u'{} beam(s) processed.'.format(len(beams)),
            u'{} Rebar element(s) created.'.format(summary.get('created', 0)),
        ]
        if summary.get('errors'):
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — used to silently cap at 12 with no
            # "...and N more" indicator at all — worse than the other
            # tabs' truncation, since there was no sign more existed.
            # TxtBeamResult is now a scrollable, read-only TextBox.
            lines.extend(summary['errors'])
        self.TxtBeamResult.Text = u'\n'.join(lines)

    def _process_beam(self, host, values, wrapper, bar_types, errors, created_rebars):
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Other', self._standard_default_cover_mm(u'beam'))
        lap_mm = None
        try:
            lap_mm = standards.lap_length_mm(
                self.ra_standard, values['bar_dia'], in_compression=False)
        except Exception:
            lap_mm = max(40.0 * values['bar_dia'], 200.0)

        curves = beam_rebar.build_beam_rebar_curves(
            self.doc, host,
            cover_mm=cover_mm,
            bar_diameter_mm=values['bar_dia'],
            n_top_bars=values['n_top'],
            n_bottom_bars=values['n_bottom'],
            stirrup_spacing_mm=values['stirrup_spacing'],
            stirrup_bar_diameter_mm=values['stirrup_dia'],
            stirrup_start_offset_mm=values['end_offset'],
            stirrup_end_offset_mm=values['end_offset'],
            stock_length_mm=values['stock_length'],
            lap_length_mm=lap_mm,
            densify_ends=values.get('densify_ends', False),
            dense_spacing_mm=values.get('dense_spacing'),
            confine_length_mm=values.get('confine_length'))

        for w in curves.get('warnings', []):
            errors.append(u'Beam {}: {}'.format(get_id_value(host.Id), w))

        bar_type_long = bar_types.get(values['bar_dia'])
        long_normal = curves.get('long_bar_normal') or DB.XYZ.BasisZ

        def _create_bar_group_or_fallback(group, label, layer):
            """
            One entry from top_bar_sets/bottom_bar_sets: try ONE Rebar
            Set for `count` parallel bars (the optimisation — n
            individual elements become 1 countable Set), falling back
            to individual create_from_curves calls (all_curves) if the
            Set attempt fails, matching the same try/fallback shape
            already established for stirrup_sets above.
            """
            n = group.get('count', 1)
            if n > 1 and group.get('array_length_mm', 0) > 0:
                rebar = wrapper.create_rebar_set(
                    host, group['curves'], bar_type_long, group['spacing_mm'],
                    group['array_length_mm'], normal=group.get('normal', long_normal),
                    transaction_name=u'NOSA — Create {}'.format(group.get('label', label)))
                if rebar is None:
                    for chain in group.get('all_curves', [group['curves']]):
                        if not chain:
                            continue
                        rb = wrapper.create_from_curves(
                            host, chain, bar_type_long, normal=group.get('normal', long_normal),
                            transaction_name=u'NOSA — Create {}'.format(label))
                        if rb is None:
                            errors.append(u'Beam {}: {} — {}'.format(
                                get_id_value(host.Id), label, wrapper.last_error))
                        else:
                            self._stamp_layer(rb, layer)
                            created_rebars.append(rb)
                else:
                    self._stamp_layer(rebar, layer)
                    created_rebars.append(rebar)
                    if wrapper.last_error:
                        errors.append(u'Beam {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
            else:
                for chain in group.get('all_curves', [group.get('curves')]):
                    if not chain:
                        continue
                    rb = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=group.get('normal', long_normal),
                        transaction_name=u'NOSA — Create {}'.format(label))
                    if rb is None:
                        errors.append(u'Beam {}: {} — {}'.format(
                            get_id_value(host.Id), label, wrapper.last_error))
                    else:
                        self._stamp_layer(rb, layer)
                        created_rebars.append(rb)

        if bar_type_long is not None:
            top_bar_sets = curves.get('top_bar_sets')
            if top_bar_sets:
                for group in top_bar_sets:
                    _create_bar_group_or_fallback(group, u'Beam Top Bar', u'top')
            else:
                # Legacy fallback — no grouped sets returned (e.g. an
                # older beam_rebar.py without this optimisation).
                for chain in curves.get('top_bars', []):
                    if not chain:
                        continue
                    rebar = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=long_normal,
                        transaction_name=u'NOSA — Create Beam Top Bar')
                    if rebar is None:
                        errors.append(u'Beam {}: top bar — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'top')
                        created_rebars.append(rebar)

            bottom_bar_sets = curves.get('bottom_bar_sets')
            if bottom_bar_sets:
                for group in bottom_bar_sets:
                    _create_bar_group_or_fallback(group, u'Beam Bottom Bar', u'bottom')
            else:
                for chain in curves.get('bottom_bars', []):
                    if not chain:
                        continue
                    rebar = wrapper.create_from_curves(
                        host, chain, bar_type_long, normal=long_normal,
                        transaction_name=u'NOSA — Create Beam Bottom Bar')
                    if rebar is None:
                        errors.append(u'Beam {}: bottom bar — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'bottom')
                        created_rebars.append(rebar)

        bar_type_st = bar_types.get(values['stirrup_dia'])
        stirrup_sets = curves.get('stirrup_sets') or []
        if bar_type_st is not None and stirrup_sets:
            for sset in stirrup_sets:
                n = sset.get('count', 1)
                if n > 1 and sset.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, sset['curves'], bar_type_st, sset['spacing_mm'],
                        sset['array_length_mm'], normal=sset['normal'],
                        style=DBS.RebarStyle.StirrupTie,
                        transaction_name=u'NOSA — Create Beam Stirrups ({})'.format(
                            sset.get('zone', u'')))
                    if rebar is None:
                        for st_curves in sset.get('all_curves', [sset['curves']]):
                            rb = wrapper.create_from_curves(
                                host, st_curves, bar_type_st,
                                normal=sset.get('normal'),
                                style=DBS.RebarStyle.StirrupTie,
                                transaction_name=u'NOSA — Create Beam Stirrup')
                            if rb is None:
                                errors.append(u'Beam {}: stirrup — {}'.format(
                                    get_id_value(host.Id), wrapper.last_error))
                            else:
                                self._stamp_layer(rb, u'stirrup')
                                created_rebars.append(rb)
                    else:
                        self._stamp_layer(rebar, u'stirrup')
                        created_rebars.append(rebar)
                        if wrapper.last_error:
                            errors.append(u'Beam {}: stirrups {} — {}'.format(
                                get_id_value(host.Id), sset.get('zone', u''),
                                wrapper.last_error))
                else:
                    rebar = wrapper.create_from_curves(
                        host, sset['curves'], bar_type_st,
                        normal=sset.get('normal'),
                        style=DBS.RebarStyle.StirrupTie,
                        transaction_name=u'NOSA — Create Beam Stirrup')
                    if rebar is None:
                        errors.append(u'Beam {}: stirrup — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'stirrup')
                        created_rebars.append(rebar)
        elif bar_type_st is not None:
            # Legacy flat list fallback
            stirrup_normal = curves.get('long_bar_normal') or DB.XYZ.BasisZ
            for st_curves in curves.get('stirrups', []):
                rebar = wrapper.create_from_curves(
                    host, st_curves, bar_type_st, normal=stirrup_normal,
                    style=DBS.RebarStyle.StirrupTie,
                    transaction_name=u'NOSA — Create Beam Stirrup')
                if rebar is None:
                    errors.append(u'Beam {}: stirrup — {}'.format(
                        get_id_value(host.Id), wrapper.last_error))
                else:
                    self._stamp_layer(rebar, u'stirrup')
                    created_rebars.append(rebar)

    def _run_beam_reinforcement(self, beams, values):
        errors = []
        diameters = {values['bar_dia'], values['stirrup_dia']}
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []
        for host in beams:
            try:
                self._process_beam(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                errors.append(u'Beam {}: {}'.format(get_id_value(host.Id), e))
        return created_rebars, {'created': len(created_rebars), 'errors': errors}

    # ── Walls (Phase F7) ─────────────────────────────────────────────────

    def _read_wall_inputs(self):
        errors = []
        values = {}
        values['vert_dia'] = self._read_number(self.TxtWallVertDia.Text, u'Vertical diameter', errors)
        values['vert_spacing'] = self._read_number(
            self.TxtWallVertSpacing.Text, u'Vertical spacing', errors)
        values['horiz_dia'] = self._read_number(
            self.TxtWallHorizDia.Text, u'Horizontal diameter', errors)
        values['horiz_spacing'] = self._read_number(
            self.TxtWallHorizSpacing.Text, u'Horizontal spacing', errors)
        values['both_faces'] = self.ChkWallBothFaces.IsChecked == True
        # BUG FIX (2026-09-01) — reported live: End/Top U-bars (and the
        # main mesh) always assumed vertical = outer layer, no way to
        # flip it. This selector controls both.
        values['vert_is_outer'] = self.ChkWallVertOuter.IsChecked == True
        values['include_ties'] = self.ChkWallTies.IsChecked == True
        if values['include_ties']:
            values['tie_dia'] = self._read_number(
                self.TxtWallTieDia.Text, u'Tie diameter', errors)
            values['tie_spacing'] = self._read_number(
                self.TxtWallTieSpacing.Text, u'Tie spacing', errors)
        values['include_end_ubars'] = self.ChkWallEndUBars.IsChecked == True
        if values['include_end_ubars']:
            values['ubar_dia'] = self._read_number(
                self.TxtWallUBarDia.Text, u'U-bar diameter', errors)
            values['ubar_spacing'] = self._read_number(
                self.TxtWallUBarSpacing.Text, u'U-bar spacing', errors)
        values['include_starter_bars'] = self.ChkWallStarters.IsChecked == True
        if values['include_starter_bars']:
            try:
                sl = float(self.TxtWallStarterLength.Text)
            except (TypeError, ValueError):
                errors.append(u'"Starter length" must be a number (0 = auto).')
                sl = None
            if sl is not None and sl < 0:
                errors.append(u'"Starter length" cannot be negative.')
                sl = None
            values['starter_length'] = sl if (sl and sl > 0) else None
        # PHASE F7.18 (2026-09-02, explicit request) — L-shaped starters
        # into whatever foundation (isolated/strip footing or floor/mat
        # slab) is detected below the wall, distinct from include_
        # starter_bars above (a plain straight extension, no foundation
        # detection or hook).
        values['foundation_starters'] = self.ChkWallFoundationStarters.IsChecked == True
        if values['foundation_starters']:
            values['foundation_anchor_mm'] = self._read_number(
                self.TxtWallFoundationAnchor.Text, u'Foundation starter anchor length', errors)
            values['foundation_splice_mm'] = self._read_number(
                self.TxtWallFoundationSplice.Text, u'Foundation starter splice length', errors)
        values['stock_length'] = self._read_number(
            self.TxtWallStockLength.Text, u'Max stock length', errors)
        if values.get('stock_length') is not None and values['stock_length'] < 1000.0:
            errors.append(u'"Max stock length" must be at least 1000 mm.')
        if errors:
            forms.alert(u'\n'.join(errors))
            return None
        return values

    def WallTies_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallTies.IsEnabled = self.ChkWallTies.IsChecked == True
        self._update_wall_preview()

    def WallEndUBars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallEndUBars.IsEnabled = self.ChkWallEndUBars.IsChecked == True
        self._update_wall_preview()

    def WallStarters_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallStarters.IsEnabled = self.ChkWallStarters.IsChecked == True
        self._update_wall_preview()

    def WallFoundationStarters_Click(self, sender, args):
        # PHASE F7.18 (2026-09-02) — no preview support yet, same
        # reasoning as ColFoundationStarters_Click.
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelWallFoundationStarters.IsEnabled = self.ChkWallFoundationStarters.IsChecked == True

    def WallPreview_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_wall_preview()

    def RunWallReinforcement_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        values = self._read_wall_inputs()
        if values is None:
            return
        self._reinforcement_handler.pending = {'mode': 'walls', 'values': values}
        self.Hide()
        self._reinforcement_event.Raise()

    def _show_wall_result(self, walls, summary):
        lines = [
            u'{} wall(s) processed.'.format(len(walls)),
            u'{} Rebar element(s) created.'.format(summary.get('created', 0)),
        ]
        if summary.get('errors'):
            lines.append(u'')
            lines.append(u'{} issue(s):'.format(len(summary['errors'])))
            # BUG FIX (2026-09-01) — same fix as _show_beam_result.
            lines.extend(summary['errors'])
        self.TxtWallResult.Text = u'\n'.join(lines)

    def _process_wall(self, host, values, wrapper, bar_types, errors, created_rebars):
        cover_mm = re_engine.get_native_cover_mm(
            self.doc, host, u'Exterior', self._standard_default_cover_mm(u'wall'))
        lap_mm = None
        try:
            lap_mm = standards.lap_length_mm(
                self.ra_standard, values['vert_dia'], in_compression=False)
        except Exception:
            lap_mm = max(40.0 * values['vert_dia'], 200.0)
        # BUG FIX (2026-09-01) — horiz_dia's own lap, not vert_dia's
        # reused unchanged (see wall_rebar.build_wall_reinforcement's
        # own docstring note on horiz_lap_length_mm).
        horiz_lap_mm = None
        try:
            horiz_lap_mm = standards.lap_length_mm(
                self.ra_standard, values['horiz_dia'], in_compression=False)
        except Exception:
            horiz_lap_mm = max(40.0 * values['horiz_dia'], 200.0)

        reinforcement = wall_rebar.build_wall_reinforcement(
            self.doc, host,
            cover_mm=cover_mm,
            vert_dia_mm=values['vert_dia'],
            vert_spacing_mm=values['vert_spacing'],
            horiz_dia_mm=values['horiz_dia'],
            horiz_spacing_mm=values['horiz_spacing'],
            both_faces=values['both_faces'],
            include_ties=values.get('include_ties', False),
            tie_dia_mm=values.get('tie_dia'),
            tie_spacing_mm=values.get('tie_spacing', 400.0),
            include_end_ubars=values.get('include_end_ubars', False),
            ubar_dia_mm=values.get('ubar_dia'),
            ubar_spacing_mm=values.get('ubar_spacing'),
            include_top_ubars=values.get('include_end_ubars', False),
            include_starter_bars=values.get('include_starter_bars', False),
            starter_length_mm=values.get('starter_length'),
            stock_length_mm=values.get('stock_length', 12000.0),
            lap_length_mm=lap_mm,
            horiz_lap_length_mm=horiz_lap_mm,
            vert_is_outer=values.get('vert_is_outer', True))

        for w in reinforcement.get('warnings', []):
            errors.append(u'Wall {}: {}'.format(get_id_value(host.Id), w))

        def _create_curves(curves, bar_type, normal, label, style=None, layer=None):
            if bar_type is None or not curves:
                return
            rebar = wrapper.create_from_curves(
                host, curves, bar_type, normal=normal, style=style,
                transaction_name=u'NOSA — Create {}'.format(label))
            if rebar is None:
                errors.append(u'Wall {}: {} — {}'.format(
                    get_id_value(host.Id), label, wrapper.last_error))
            else:
                self._stamp_layer(rebar, layer)
                created_rebars.append(rebar)

        bar_type_v = bar_types.get(values['vert_dia'])
        first_vertical = len(created_rebars)
        if bar_type_v is not None:
            for vs in reinforcement.get('vertical_sets', []):
                if vs.get('count', 1) > 1 and vs.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, vs['curves'], bar_type_v, vs['spacing_mm'],
                        vs['array_length_mm'], normal=vs['normal'],
                        transaction_name=u'NOSA — Create Wall Vertical Mesh')
                    if rebar is None:
                        errors.append(u'Wall {}: vertical — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'vertical')
                        created_rebars.append(rebar)
                else:
                    _create_curves(vs['curves'], bar_type_v, vs.get('normal'),
                                   vs.get('label', u'Wall Vertical'), layer=u'vertical')

        vertical_rebars = created_rebars[first_vertical:]

        bar_type_h = bar_types.get(values['horiz_dia'])
        if bar_type_h is not None:
            for hs in reinforcement.get('horizontal_sets', []):
                if hs.get('count', 1) > 1 and hs.get('array_length_mm', 0) > 0:
                    rebar = wrapper.create_rebar_set(
                        host, hs['curves'], bar_type_h, hs['spacing_mm'],
                        hs['array_length_mm'], normal=hs['normal'],
                        transaction_name=u'NOSA — Create Wall Horizontal Mesh')
                    if rebar is None:
                        errors.append(u'Wall {}: horizontal — {}'.format(
                            get_id_value(host.Id), wrapper.last_error))
                    else:
                        self._stamp_layer(rebar, u'horizontal')
                        created_rebars.append(rebar)
                else:
                    _create_curves(hs['curves'], bar_type_h, hs.get('normal'),
                                   hs.get('label', u'Wall Horizontal'), layer=u'horizontal')

        tie_dia = values.get('tie_dia') or values['horiz_dia']
        bar_type_t = bar_types.get(tie_dia)
        if bar_type_t is not None:
            for tie in reinforcement.get('ties', []):
                _create_curves(tie['curves'], bar_type_t, tie.get('normal'),
                               tie.get('label', u'Wall Tie'),
                               style=DBS.RebarStyle.StirrupTie, layer=u'tie')

        # BUG FIX (2026-09-01) — End/Top U-bars now come back from
        # wall_rebar.py as {'sets':[...],'bars':[...]} (grouped by end/
        # position — every height/position along one end or the wall
        # head shares an identical shape), routed through the same
        # _create_grouped_bars helper footings/floors already use for
        # this exact open leg-back-leg U topology: Set first, FreeForm-
        # group fallback, individual bars only as the true last resort
        # — instead of always creating N loose individual elements.
        ubar_dia = values.get('ubar_dia') or values['vert_dia']
        bar_type_u = bar_types.get(ubar_dia)
        if bar_type_u is not None:
            self._create_grouped_bars(
                wrapper, host, reinforcement.get('end_ubars', {'sets': [], 'bars': []}),
                bar_type_u, errors, created_rebars, u'Wall End U-Bar', layer=u'end_ubar')
            self._create_grouped_bars(
                wrapper, host, reinforcement.get('top_ubars', {'sets': [], 'bars': []}),
                bar_type_u, errors, created_rebars, u'Wall Top U-Bar', layer=u'top_ubar')

        # PHASE F7.18 (2026-09-02, explicit request — "Starter bars con
        # forma de L en columnas y muros... unidas a la cimentación") —
        # one starter per vertical-bar position along the wall's own
        # length, reaching down into whatever foundation is detected
        # below it.
        if values.get('foundation_starters') and bar_type_v is not None:
            points = re_engine.unique_plan_points(
                [p for r in vertical_rebars for p in re_engine.rebar_bar_plan_points(r)])
            starters = wall_rebar.build_wall_foundation_starters(
                self.doc, host, points, values['vert_dia'], values['vert_dia'],
                values['foundation_anchor_mm'], values['foundation_splice_mm'],
                foundation_cover_mm=cover_mm)
            hook_90 = re_engine.get_hook_type_by_angle(self.doc, 90.0)
            if hook_90 is None:
                errors.append(u'Wall {}: foundation starters — no 90° RebarHookType '
                              u'found in this project; created WITHOUT hooks (not '
                              u'normative anchorage).'.format(get_id_value(host.Id)))
            self._create_foundation_starter_bars(
                wrapper, host, starters, bar_type_v, hook_90, u'Wall',
                errors, created_rebars)

    def _run_wall_reinforcement(self, walls, values):
        errors = []
        diameters = {values['vert_dia'], values['horiz_dia']}
        if values.get('include_ties'):
            diameters.add(values.get('tie_dia') or values['horiz_dia'])
        if values.get('include_end_ubars'):
            diameters.add(values.get('ubar_dia') or values['vert_dia'])
        bar_types = {}
        for dia_mm in diameters:
            bt = re_engine.get_bar_type_by_diameter(self.doc, dia_mm)
            if bt is None:
                errors.append(u'No RebarBarType found for {}mm — bars of that '
                              u'diameter will be skipped.'.format(dia_mm))
            bar_types[dia_mm] = bt

        wrapper = re_engine.RebarWrapper(self.doc)
        created_rebars = []
        for host in walls:
            try:
                self._process_wall(host, values, wrapper, bar_types, errors, created_rebars)
            except Exception as e:
                errors.append(u'Wall {}: {}'.format(get_id_value(host.Id), e))
        return created_rebars, {'created': len(created_rebars), 'errors': errors}

    # ── Detailing & Tools — dashboard (Phase 1 placeholders) ────────────────
    # Every handler below is wired (not disabled) so the button gives real
    # feedback when clicked, but does nothing yet — each one's actual logic
    # is a Phase 5 (Modify/Detailing Tools) or later deliverable. Kept as
    # one line per handler here deliberately: there is no shared behaviour
    # to factor out yet, and pre-building an abstraction for behaviour that
    # doesn't exist yet would be exactly the speculative generality this
    # project avoids elsewhere.

    # ── Batch Manager (Phase F1) ─────────────────────────────────────────

    def _refresh_batch_list(self):
        """Repopulates LstBatches from rebar_batch.RebarBatch.list_batches
        — one formatted row per distinct batch_id, storing the RAW
        batch_id string as each ListBoxItem's own Tag so Select/Delete
        don't need to re-parse the displayed text."""
        self.LstBatches.Items.Clear()
        try:
            batches = rebar_batch.RebarBatch.list_batches(self.doc)
        except Exception as e:
            forms.alert(u'Could not list batches:\n{}'.format(e))
            return
        if not batches:
            item = SWC.ListBoxItem()
            item.Content = u'(no NOSA RebarAutomate batches found in this document)'
            item.IsEnabled = False
            self.LstBatches.Items.Add(item)
            return
        for b in batches:
            item = SWC.ListBoxItem()
            item.Content = u'{}   —   {} bar(s)   —   {}'.format(
                b['batch_id'], b['count'], b.get('standard_code') or u'?')
            item.Tag = b['batch_id']
            self.LstBatches.Items.Add(item)

    def _selected_batch_id(self):
        selected = self.LstBatches.SelectedItem
        if selected is None:
            return None
        return getattr(selected, 'Tag', None)

    def RefreshBatches_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._refresh_batch_list()

    def SelectBatch_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        batch_id = self._selected_batch_id()
        if not batch_id:
            forms.alert(u'Select a batch from the list first.')
            return
        try:
            ids = rebar_batch.RebarBatch.select_batch(self.doc, batch_id)
        except Exception as e:
            forms.alert(u'Could not select batch {}:\n{}'.format(batch_id, e))
            return
        if not ids:
            forms.alert(u'No elements found for batch {} — it may already be deleted.'.format(
                batch_id))
            return
        self.uidoc.Selection.SetElementIds(List[DB.ElementId](ids))
        forms.alert(u'{} element(s) from batch {} selected in the model.'.format(
            len(ids), batch_id))

    def DeleteBatch_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        batch_id = self._selected_batch_id()
        if not batch_id:
            forms.alert(u'Select a batch from the list first.')
            return
        confirmed = forms.alert(
            u'Delete every element from batch {}? Elements marked '
            u'"Finalized" are protected and will be skipped.'.format(batch_id),
            title=u'NOSA RebarAutomate — Delete Batch', yes=True, no=True)
        if not confirmed:
            return
        try:
            result = rebar_batch.RebarBatch.delete_batch(self.doc, batch_id)
        except Exception as e:
            forms.alert(u'Delete batch failed:\n{}'.format(e))
            return
        lines = [
            u'{} element(s) deleted.'.format(len(result['deleted'])),
            u'{} element(s) protected (Finalized) and kept.'.format(len(result['protected'])),
        ]
        if result['errors']:
            lines.append(u'{} error(s):'.format(len(result['errors'])))
            lines.extend(result['errors'][:10])
        forms.alert(u'\n'.join(lines))
        self._refresh_batch_list()

    def GenerateSchedule_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Rebar schedule generation is not implemented yet — planned for Phase 5.')

    def Lap_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Lap (join collinear bars) is not implemented yet — planned for Phase 5.')

    def Split_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Split (to commercial stock length) is not implemented yet — planned for '
                    u'Phase 5. Note: the underlying math (rebar_engine.split_rebar_by_stock_length) '
                    u'already exists from Phase 1 — this tool would expose it for already-placed bars.')

    def Extend_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Extend (lengthen hooks/legs) is not implemented yet — planned for Phase 5.')

    def CopyToSimilar_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Copy to similar hosts is not implemented yet — planned for Phase 5.')

    def DeleteHostRebars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Delete Host Rebars is not implemented yet — planned for Phase 5.')

    def ToggleSolids_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Show/Hide Rebar as Solids is not implemented yet — planned for Phase 5.')

    # ── Detailing (Phase F6) ─────────────────────────────────────────────

    def _populate_detailing_combos(self):
        """Fill CmbRebarTagType / CmbMraType from families loaded in the project."""
        # Rebar tag types
        self.CmbRebarTagType.Items.Clear()
        tag_types = []
        try:
            tag_types = rebar_detailing.list_rebar_tag_types(self.doc)
        except Exception:
            tag_types = []
        if not tag_types:
            item = SWC.ComboBoxItem()
            item.Content = u'(no rebar tag types loaded)'
            item.IsEnabled = False
            self.CmbRebarTagType.Items.Add(item)
        else:
            # IronPython: do NOT use lambda t: t.Name — free-var lookup
            # raises NameError: Name. Use getattr / explicit helper.
            def _type_name(el):
                return getattr(el, 'Name', None) or u''
            for tt in sorted(tag_types, key=_type_name):
                item = SWC.ComboBoxItem()
                item.Content = _type_name(tt)
                item.Tag = tt.Id
                self.CmbRebarTagType.Items.Add(item)
            self.CmbRebarTagType.SelectedIndex = 0

        # Multi-rebar annotation types
        self.CmbMraType.Items.Clear()
        mra_types = []
        try:
            mra_types = rebar_detailing.list_mra_types(self.doc)
        except Exception:
            mra_types = []
        if not mra_types:
            item = SWC.ComboBoxItem()
            item.Content = u'(no multi-rebar annotation types loaded)'
            item.IsEnabled = False
            self.CmbMraType.Items.Add(item)
        else:
            def _mra_name(el):
                return getattr(el, 'Name', None) or u''
            for mt in sorted(mra_types, key=_mra_name):
                item = SWC.ComboBoxItem()
                item.Content = _mra_name(mt)
                item.Tag = mt.Id
                self.CmbMraType.Items.Add(item)
            self.CmbMraType.SelectedIndex = 0

    def _combo_selected_element_id(self, combo):
        selected = combo.SelectedItem
        if selected is None:
            return None
        return getattr(selected, 'Tag', None)

    def _selected_rebars(self):
        """Rebars currently selected in the model (OST_Rebar only)."""
        rebars = []
        try:
            for eid in self.uidoc.Selection.GetElementIds():
                elem = self.doc.GetElement(eid)
                if elem is None:
                    continue
                try:
                    if elem.Category and get_id_value(elem.Category.Id) == get_id_value(
                            DB.ElementId(DB.BuiltInCategory.OST_Rebar)):
                        rebars.append(elem)
                except Exception:
                    continue
        except Exception:
            pass
        return rebars

    def _selected_detail_hosts(self):
        """Footings / floors / columns currently selected (for detail sections)."""
        hosts = []
        allowed = set([_cat_id('OST_StructuralFoundation'), _cat_id('OST_Floors'), _cat_id('OST_StructuralColumns')])
        try:
            for eid in self.uidoc.Selection.GetElementIds():
                elem = self.doc.GetElement(eid)
                if elem is None or elem.Category is None:
                    continue
                try:
                    if get_id_value(elem.Category.Id) in allowed:
                        hosts.append(elem)
                except Exception:
                    continue
        except Exception:
            pass
        return hosts

    def AutoTag_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        rebars = self._selected_rebars()
        if not rebars:
            forms.alert(u'Select one or more rebar elements in the model first.',
                        title=u'NOSA — Auto Tag')
            return

        view = self.doc.ActiveView
        if view is None or getattr(view, 'IsTemplate', False):
            forms.alert(u'Switch to a model view (not a template) before tagging.',
                        title=u'NOSA — Auto Tag')
            return

        tag_type_id = self._combo_selected_element_id(self.CmbRebarTagType)
        try:
            with revit.Transaction(u'NOSA — Auto Tag Rebar'):
                tags, errors = rebar_detailing.create_rebar_tags_smart(
                    self.doc, view, rebars,
                    use_param_offsets=True,
                    tag_type_id=tag_type_id,
                    add_leader=False)
        except Exception as e:
            forms.alert(u'Auto Tag failed:\n{}'.format(e), title=u'NOSA — Auto Tag')
            return

        msg = u'Created {} tag(s) for {} selected rebar(s).'.format(len(tags), len(rebars))
        if errors:
            msg += u'\n\n{} warning(s):\n{}'.format(
                len(errors), u'\n'.join(errors[:8]))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto Tag')

    def AutoMRA_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        rebars = self._selected_rebars()
        if len(rebars) < 1:
            forms.alert(
                u'Select one or more rebar elements (typically a parallel set) '
                u'in the model first.',
                title=u'NOSA — Auto MRA')
            return

        view = self.doc.ActiveView
        if view is None or getattr(view, 'IsTemplate', False):
            forms.alert(u'Switch to a model view (not a template) before creating an MRA.',
                        title=u'NOSA — Auto MRA')
            return

        mra_type_id = self._combo_selected_element_id(self.CmbMraType)
        mra_type = self.doc.GetElement(mra_type_id) if mra_type_id else None
        if mra_type is None:
            forms.alert(
                u'No Multi-Rebar Annotation type is available in this project.\n'
                u'Load a Multi-Rebar Annotation family first (Project Browser → '
                u'Families → Annotation Symbols → Multi-Rebar Annotations).',
                title=u'NOSA — Auto MRA')
            return

        try:
            with revit.Transaction(u'NOSA — Auto Multi-Rebar Annotation'):
                mra = rebar_detailing.create_multi_rebar_annotation(
                    self.doc, view, rebars, mra_type=mra_type, dim_offset_mm=300.0)
        except Exception as e:
            forms.alert(u'Auto MRA failed:\n{}'.format(e), title=u'NOSA — Auto MRA')
            return

        if mra is None:
            msg = (u'Could not create Multi-Rebar Annotation for {} selected bar(s).\n'
                   u'Check that they are the same category, roughly parallel, and '
                   u'visible in the active view.'.format(len(rebars)))
            self.TxtDetailingStatus.Text = msg
            forms.alert(msg, title=u'NOSA — Auto MRA')
            return

        msg = u'Multi-Rebar Annotation created for {} bar(s).'.format(len(rebars))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto MRA')

    def AutoSections_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        hosts = self._selected_detail_hosts()
        if not hosts:
            forms.alert(
                u'Select one or more footings, floors, or columns in the model first.',
                title=u'NOSA — Auto Sections')
            return

        created = 0
        errors = []
        try:
            with revit.Transaction(u'NOSA — Auto Detail Sections'):
                for host in hosts:
                    sections, host_errors = rebar_detailing.create_orthogonal_detail_sections(
                        self.doc, host)
                    created += len(sections)
                    for err in host_errors:
                        errors.append(u'{}: {}'.format(get_id_value(host.Id), err))
        except Exception as e:
            forms.alert(u'Auto Sections failed:\n{}'.format(e),
                        title=u'NOSA — Auto Sections')
            return

        msg = u'Created {} detail section(s) for {} host(s).'.format(created, len(hosts))
        if errors:
            msg += u'\n\n{} warning(s):\n{}'.format(
                len(errors), u'\n'.join(errors[:8]))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Auto Sections')

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
