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
                                     '..', '..', '..', '..', 'lib'))
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
rebar_preview = load_module('rebar_preview', os.path.join(_HERE, 'rebar_preview.py'))
# PHASE F1
rebar_batch = load_module('rebar_batch', os.path.join(_HERE, 'rebar_batch.py'))
rebar_project = load_module('rebar_project', os.path.join(_HERE, 'rebar_project.py'))
_version_mod = load_module('rebarautomate_version', os.path.join(_HERE, '_version.py'))

_FOUNDATION_CAT_ID = get_id_value(DB.ElementId(DB.BuiltInCategory.OST_StructuralFoundation))
_FLOOR_CAT_ID = get_id_value(DB.ElementId(DB.BuiltInCategory.OST_Floors))
_COLUMN_CAT_ID = get_id_value(DB.ElementId(DB.BuiltInCategory.OST_StructuralColumns))

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
                sel_filter = _CategorySelectionFilter([_COLUMN_CAT_ID])
                prompt = u'Select Structural Columns to reinforce, then click Finish.'
            else:
                sel_filter = _CategorySelectionFilter([_FOUNDATION_CAT_ID, _FLOOR_CAT_ID])
                prompt = (u'Select Structural Foundations and/or Floors to reinforce, '
                          u'then click Finish.')

            try:
                refs = uidoc.Selection.PickObjects(ObjectType.Element, sel_filter, prompt)
            except OperationCanceledException:
                # Silent cancel — user backed out of selection. Focus
                # returns to the window via the outer finally below.
                return

            elements = [uidoc.Document.GetElement(r.ElementId) for r in refs]

            if mode == 'columns':
                if not elements:
                    forms.alert(u'No Structural Columns selected.')
                    return
                window.SetLoading(True, u'Generating column reinforcement…')
                try:
                    # PHASE F1 — RebarBatch wraps the SAME
                    # _run_column_reinforcement call in one
                    # TransactionGroup and stamps provenance on every
                    # created Rebar. It does not change what geometry
                    # gets generated — generate_fn is this exact,
                    # unchanged call.
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'))
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
            else:
                footings = [e for e in elements if e.Category is not None and
                            get_id_value(e.Category.Id) == _FOUNDATION_CAT_ID]
                floors = [e for e in elements if e.Category is not None and
                          get_id_value(e.Category.Id) == _FLOOR_CAT_ID]
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
                    # PHASE F1 — same wrapping as the column branch
                    # above; generate_fn is the exact, unchanged
                    # _run_reinforcement call.
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', u'EHE-08'))
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

        # PHASE F1 — shared-param sealing, once per document. On the
        # VERY FIRST launch on a given document (no rebar_project.json
        # saved for it yet — rebar_project.exists returns False), ask
        # ONCE whether to also insert NOSA's parameters into the
        # office's own shared-parameter file (default No — never
        # touches it uninvited); the answer is saved and never asked
        # again for this document. ensure_bound itself is idempotent
        # and safe to re-run on every launch (Decision 5.A: it swaps
        # app.SharedParametersFilename to NOSA's own .txt just long
        # enough to bind, then restores the original path).
        self.ra_project = rebar_project.load(self.doc)
        if not rebar_project.exists(self.doc):
            insert_into_office_file = forms.alert(
                u'Would you also like to insert NOSA\'s shared parameters into your '
                u'office\'s own shared parameter file? (The project\'s own bindings '
                u'are created either way, even if you answer No.)',
                title=u'NOSA RebarAutomate — Shared Parameters',
                yes=True, no=True)
            self.ra_project['insert_shared_params_into_user_file'] = bool(insert_into_office_file)
            rebar_project.save(self.doc, self.ra_project)
        self.ra_generator_version = _version_mod.RA_VERSION
        
        # ALWAYS verify and create shared parameters on every launch
        # (ensure_bound is idempotent and safe to re-run)
        try:
            print(u'\n' + u'='*80)
            print(u'NOSA RebarAutomate — Verifying shared parameters...')
            self._shared_params_report = shared_params.ensure_bound(
                self.doc,
                insert_into_user_file=self.ra_project.get(
                    'insert_shared_params_into_user_file', False))
            
            # Report results to console
            bound_count = len(self._shared_params_report.get('bound', []))
            already_count = len(self._shared_params_report.get('already', []))
            skipped_count = len(self._shared_params_report.get('skipped', []))
            error_count = len(self._shared_params_report.get('errors', []))
            
            print(u'  ✓ Newly bound: {} parameters'.format(bound_count))
            print(u'  ✓ Already bound: {} parameters'.format(already_count))
            if skipped_count > 0:
                print(u'  ⚠ Skipped: {} parameters'.format(skipped_count))
            if error_count > 0:
                print(u'  ✗ Errors: {} parameters'.format(error_count))
                for err in self._shared_params_report.get('errors', []):
                    print(u'    - {}'.format(err))
            
            print(u'='*80 + u'\n')
            
            # Show alert if critical errors occurred
            if error_count > 0:
                forms.alert(
                    u'WARNING: {} error(s) occurred while creating shared parameters.\n\n'
                    u'Check the pyRevit console (Ctrl+F8) for details.\n\n'
                    u'Some NOSA features may not work correctly.'.format(error_count),
                    title=u'NOSA RebarAutomate — Shared Parameters',
                    warn_icon=True)
            elif bound_count > 0:
                # First time binding succeeded
                forms.alert(
                    u'Successfully created {} NOSA shared parameters.\n\n'
                    u'These parameters are now available on rebar elements:\n'
                    u'• NOSA_Rebar_Batch_Id\n'
                    u'• NOSA_Rebar_Mark\n'
                    u'• NOSA_Rebar_Number\n'
                    u'• NOSA_Rebar_Shape_Code\n'
                    u'• NOSA_Rebar_Shape_Params\n'
                    u'• ... and more'.format(bound_count),
                    title=u'NOSA RebarAutomate — Shared Parameters')
                
        except Exception as e:
            self._shared_params_report = {'bound': [], 'already': [], 'skipped': [],
                                           'errors': [u'ensure_bound failed: {}'.format(e)]}
            print(u'\n✗ CRITICAL ERROR creating shared parameters: {}\n'.format(e))
            forms.alert(
                u'CRITICAL ERROR: Could not create shared parameters.\n\n'
                u'Error: {}\n\n'
                u'Check the pyRevit console (Ctrl+F8) for details.\n\n'
                u'NOSA features will not work until this is resolved.'.format(e),
                title=u'NOSA RebarAutomate — Error',
                warn_icon=True)

        # PHASE F2 — normativa (rebar standard) profile, resolved once at
        # launch and re-resolved whenever the user changes the "Standard:"
        # dropdown. self.ra_standard is the full profile dict consumed by
        # standards.cover_for/lap_length_mm/etc; self.ra_project holds the
        # persisted code string (rebar_project.json's 'standard_code').
        self.ra_standard = self._load_standard(self.ra_project.get('standard_code', u'EHE-08'))
        self._populate_standard_dropdown()
        self._populate_project_header()

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

    # ── normativa (rebar standard) — PHASE F2 ───────────────────────────

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
            # Cargar rebar_schedule con load_module (IronPython compatible)
            import imp
            rebar_schedule = imp.load_source('rebar_schedule',
                os.path.join(os.path.dirname(__file__), 'rebar_schedule.py'))
            
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
            summary_msg += u'Total length: {:.2f} m\n\n'.format(stats['total_length_m'])
            summary_msg += u'By diameter:\n'
            for dia in sorted(stats['by_diameter'].keys()):
                dia_stats = stats['by_diameter'][dia]
                summary_msg += u'  Ø{} mm: {} bars, {:.2f} m\n'.format(
                    dia, dia_stats['count'], dia_stats['length_m']
                )
            
            # Mostrar summary en UI
            self.TxtScheduleSummary.Text = u'{} positions, {} bars, {:.1f} m total'.format(
                stats['total_positions'], stats['total_bars'], stats['total_length_m']
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
            import os
            
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

        try:
            data = rebar_preview.compute_section_preview(
                width_mm, thickness_mm, cover, dia_x, dia_y,
                include_top, top_cover, top_dia_x, top_dia_y,
                include_perimeter_ubars=include_ubars,
                x_anchor_dia_mm=x_anchor_dia, y_anchor_dia_mm=y_anchor_dia)
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
            if cat_id == _FOUNDATION_CAT_ID:
                footings.append(elem)
            elif cat_id == _FLOOR_CAT_ID:
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
            lines.extend(summary['errors'][:12])
            if len(summary['errors']) > 12:
                lines.append(u'... and {} more.'.format(len(summary['errors']) - 12))
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
        for line in dowels['bars']:
            rebar = wrapper.create_from_curves(
                host, [line], bar_type,
                start_hook=hook_type, end_hook=None,
                start_hook_orientation=_HOOK_ORIENTATION if hook_type else None,
                normal=dowels['face_normal'],
                transaction_name=u'NOSA — Create Footing Dowel')
            if rebar is None:
                errors.append(u'Footing {}: dowel — {}'.format(get_id_value(host.Id), wrapper.last_error))
            else:
                created_rebars.append(rebar)

    def _create_grouped_bars(self, wrapper, host, grouped, bar_type, errors, created_rebars, label):
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
            if len(materialized) >= 2:
                curve_groups = [b['curves'] for b in materialized]
                ff_rebar = wrapper.create_freeform_group(
                    host, curve_groups, bar_type,
                    transaction_name=u'NOSA — Create {} (FreeForm fallback)'.format(label))
                if ff_rebar is not None:
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
                        created_rebars.append(rb)
            else:
                errors.append(u'Host {}: {} (set) — {}'.format(
                    get_id_value(host.Id), label, wrapper.last_error))

        loose_bars = grouped.get('bars', [])
        freeform_candidates = [b for b in loose_bars if b.get('style') is None]
        fallback_bars = [b for b in loose_bars if b.get('style') is not None]

        if len(freeform_candidates) >= 2:
            curve_groups = [b['curves'] for b in freeform_candidates]
            rebar = wrapper.create_freeform_group(
                host, curve_groups, bar_type,
                transaction_name=u'NOSA — Create {} (FreeForm)'.format(label))
            if rebar is not None:
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
            include_side_rebar=values['include_side_rebar'],
            side_diameter_mm=values.get('side_diameter'),
            side_spacing_mm=values.get('side_spacing'),
            include_perimeter_closure_ubars=values['include_perimeter_ubars'],
            x_anchor_ubar_dia_mm=values.get('x_anchor_ubar_dia'),
            x_anchor_ubar_spacing_mm=values.get('x_anchor_ubar_spacing'),
            y_anchor_ubar_dia_mm=values.get('y_anchor_ubar_dia'),
            y_anchor_ubar_spacing_mm=values.get('y_anchor_ubar_spacing'),
            max_stock_length_mm=values['max_stock_length'])

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
            errors, created_rebars, u'Footing Bottom Mat (B1)')
        self._create_grouped_bars(
            wrapper, host, bottom['along_y'], bar_types.get(values['dia_y']),
            errors, created_rebars, u'Footing Bottom Mat (B2)')

        if reinforcement['top_mat'] is not None:
            top = reinforcement['top_mat']
            self._create_grouped_bars(
                wrapper, host, top['along_x'], bar_types.get(values['top_dia_x']),
                errors, created_rebars, u'Footing Top Mat (T1)')
            self._create_grouped_bars(
                wrapper, host, top['along_y'], bar_types.get(values['top_dia_y']),
                errors, created_rebars, u'Footing Top Mat (T2)')

        if reinforcement.get('perimeter_closure_ubars') is not None:
            closure = reinforcement['perimeter_closure_ubars']
            self._create_grouped_bars(
                wrapper, host, closure['x_bars'], bar_types.get(values.get('x_anchor_ubar_dia')),
                errors, created_rebars, u'Footing Perimeter Closure U-Bar (X-anchor)')
            self._create_grouped_bars(
                wrapper, host, closure['y_bars'], bar_types.get(values.get('y_anchor_ubar_dia')),
                errors, created_rebars, u'Footing Perimeter Closure U-Bar (Y-anchor)')
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
            max_stock_length_mm=values['max_stock_length'])

        bottom = reinforcement['bottom_mat']
        self._create_grouped_bars(
            wrapper, host, bottom['along_x'], bar_types.get(values['dia_x']),
            errors, created_rebars, u'Floor Bottom Mat (B1)')
        self._create_grouped_bars(
            wrapper, host, bottom['along_y'], bar_types.get(values['dia_y']),
            errors, created_rebars, u'Floor Bottom Mat (B2)')

        if reinforcement['top_mat'] is not None:
            top = reinforcement['top_mat']
            self._create_grouped_bars(
                wrapper, host, top['along_x'], bar_types.get(values['top_dia_x']),
                errors, created_rebars, u'Floor Top Mat (T1)')
            self._create_grouped_bars(
                wrapper, host, top['along_y'], bar_types.get(values['top_dia_y']),
                errors, created_rebars, u'Floor Top Mat (T2)')

        if reinforcement.get('perimeter_closure_ubars') is not None:
            closure = reinforcement['perimeter_closure_ubars']
            self._create_grouped_bars(
                wrapper, host, closure['x_bars'], bar_types.get(values.get('x_anchor_ubar_dia')),
                errors, created_rebars, u'Floor Perimeter Closure U-Bar (X-anchor)')
            self._create_grouped_bars(
                wrapper, host, closure['y_bars'], bar_types.get(values.get('y_anchor_ubar_dia')),
                errors, created_rebars, u'Floor Perimeter Closure U-Bar (Y-anchor)')
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
                    bar_inset_mm = cover + link_dia + bar_dia / 2.0
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
            if get_id_value(elem.Category.Id) == _COLUMN_CAT_ID:
                columns.append(elem)
        return columns

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
            lines.extend(summary['errors'][:12])
            if len(summary['errors']) > 12:
                lines.append(u'... and {} more.'.format(len(summary['errors']) - 12))
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
            crosstie_layout=values['crosstie_layout'])

        for w in reinforcement.get('warnings', []):
            errors.append(u'Column {}: {}'.format(get_id_value(host.Id), w))

        bar_type_vert = bar_types.get(values['bar_dia'])
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
                    created_rebars.append(rebar)

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
                    created_rebars.append(rebar)

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
                errors.append(u'Column {}: {}'.format(get_id_value(host.Id), e))

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

    def AutoMRA_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        forms.alert(u'Automatic Multi-Rebar Annotation is not implemented yet — planned for Phase 5.')

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
