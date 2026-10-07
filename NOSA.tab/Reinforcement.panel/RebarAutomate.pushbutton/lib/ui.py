# -*- coding: utf-8 -*-
import os, sys
import re

from pyrevit import forms, revit
from Autodesk.Revit import DB
from Autodesk.Revit.DB import Structure as DBS
from Autodesk.Revit.UI import IExternalEventHandler, ExternalEvent
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException
import System
import System.Windows.Media as SWM
import System.Windows.Shapes as SWS
import System.Windows.Controls as SWC
from System.Windows.Media import SolidColorBrush, Color
from System.Collections.Generic import List
from nosa_utils.telemetry import log_swallowed
_LOG = u'rebarautomate'

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.revit_helpers import get_id_value, element_name
from nosa_utils.bootstrap import load_module
from nosa_utils import shared_params
from nosa_utils import standards
from nosa_utils import transactions as nosa_tx  # T8.1: no Revit failure dialogs

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
rebar_modify = load_module('rebar_modify', os.path.join(_HERE, 'rebar_modify.py'))
rebar_partitions = load_module('rebar_partitions', os.path.join(_HERE, 'rebar_partitions.py'))
stair_rebar = load_module('stair_rebar', os.path.join(_HERE, 'stair_rebar.py'))
stair_host = load_module('stair_host', os.path.join(_HERE, 'stair_host.py'))
view_plan = load_module('view_plan', os.path.join(_HERE, 'view_plan.py'))
varying_sets = load_module('varying_sets', os.path.join(_HERE, 'varying_sets.py'))
rebar_views = load_module('rebar_views', os.path.join(_HERE, 'rebar_views.py'))
shape_images = load_module('shape_images', os.path.join(_HERE, 'shape_images.py'))
rebar_preview = load_module('rebar_preview', os.path.join(_HERE, 'rebar_preview.py'))
preview_shapes = load_module('rebar_preview_shapes', os.path.join(_HERE, 'rebar_preview_shapes.py'))
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
rebar_marking = load_module('rebar_marking', os.path.join(_HERE, 'rebar_marking.py'))
rebar_content = load_module('rebar_content', os.path.join(_HERE, 'rebar_content.py'))

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


class _CategorySelectionFilter(ISelectionFilter):
    """Restricts PickObjects to one or more OST_* category ids."""

    def __init__(self, category_ids):
        self._category_ids = set(category_ids)

    def AllowElement(self, element):
        return (element.Category is not None and
                get_id_value(element.Category.Id) in self._category_ids)

    def AllowReference(self, ref, point):
        return True


def is_ground_beam(element):
    """A line-based Structural Foundation (the NOSA 'RC Ground Beam' tie beam): reinforced as a beam."""
    try:
        return (get_id_value(element.Category.Id) == _cat_id('OST_StructuralFoundation')
                and isinstance(element.Location, DB.LocationCurve))
    except Exception:
        return False


def _is_valid_rebar_host(element):
    """True if Revit accepts rebar hosted on this element."""
    try:
        host_data = DBS.RebarHostData.GetRebarHostData(element)
        return host_data is not None and host_data.IsValidHost()
    except Exception:
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
            if not window._same_document(uiapp):
                return
            if mode == 'columns':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_StructuralColumns')])
                prompt = u'Select Structural Columns to reinforce, then click Finish.'
            elif mode == 'beams':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_StructuralFraming'),
                                                       _cat_id('OST_StructuralFoundation')])
                prompt = u'Select Structural Framing (beams) or ground beams to reinforce, then click Finish.'
            elif mode == 'walls':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_Walls')])
                prompt = u'Select Walls to reinforce, then click Finish.'
            elif mode == 'stairs':
                sel_filter = _CategorySelectionFilter([_cat_id('OST_Stairs')])
                prompt = u'Select cast-in-place Stairs to reinforce, then click Finish.'
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
            invalid = [e for e in elements if not _is_valid_rebar_host(e)]
            if invalid:
                forms.alert(u'{} selected element(s) cannot host rebar and were skipped: {}. '
                            u'Revit only accepts structural concrete hosts — for a floor or '
                            u'foundation slab, tick "Structural" and give it a concrete '
                            u'structural layer.'.format(
                                len(invalid), u', '.join(str(get_id_value(e.Id)) for e in invalid)))
                elements = [e for e in elements if e not in invalid]
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
                        standard_code=window.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
                        layers=window._pending_layers, locations=window._pending_locations,
                        mark_prefix=window._partition())
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
                elements = [e for e in elements if get_id_value(e.Category.Id) ==
                            _cat_id('OST_StructuralFraming') or is_ground_beam(e)]
                if not elements:
                    forms.alert(u'No Structural Framing (beams) selected.')
                    return
                window.SetLoading(True, u'Generating beam reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
                        layers=window._pending_layers, locations=window._pending_locations,
                        mark_prefix=window._partition())
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
                        standard_code=window.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
                        layers=window._pending_layers, locations=window._pending_locations,
                        mark_prefix=window._partition())
                    batch_result = batch.run(
                        lambda: window._run_wall_reinforcement(elements, values))
                    summary = dict(batch_result.summary)
                    import fit_checks   # T8.47, SMDSC 5.2: clear gaps and pitch of the meshes
                    summary['errors'] = list(batch_result.errors) + fit_checks.mesh_notes('walls', values)
                except Exception as e:
                    forms.alert(u'Wall reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_wall_result(elements, summary)
                window._refresh_batch_list()
            elif mode == 'stairs':
                if not elements:
                    forms.alert(u'No cast-in-place Stairs selected. Assembled and precast stairs '
                                u'cannot host rebar.')
                    return
                window.SetLoading(True, u'Generating stair reinforcement…')
                try:
                    batch = rebar_batch.RebarBatch(
                        window.doc, standard=window.ra_standard,
                        generator_version=window.ra_generator_version,
                        standard_code=window.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
                        layers=window._pending_layers, locations=window._pending_locations,
                        mark_prefix=window._partition())
                    batch_result = batch.run(
                        lambda: window._run_stair_reinforcement(elements, values))
                    summary = dict(batch_result.summary)
                    summary['errors'] = batch_result.errors
                except Exception as e:
                    forms.alert(u'Stair reinforcement generation failed:\n{}'.format(e))
                    return
                finally:
                    window.SetLoading(False)
                window._show_stair_result(elements, summary)
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
                        standard_code=window.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE),
                        layers=window._pending_layers, locations=window._pending_locations,
                        mark_prefix=window._partition())
                    batch_result = batch.run(
                        lambda: window._run_reinforcement(footings, floors, values))
                    summary = dict(batch_result.summary)
                    import fit_checks   # T8.47, SMDSC 5.2: clear gaps and pitch of the meshes
                    summary['errors'] = (list(batch_result.errors)
                                         + fit_checks.mesh_notes('footings_floors', values))
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


# Varying sets of trimmed 25 mm rows (floor_rebar.trim_to_step_mm): ends up to one step off the
# faces are accepted, then moved half a step inside so the rounded-up cut length keeps the cover
VARYING_STEP_TOLERANCE_MM = 30.0
VARYING_END_MARGIN_MM = 12.5

_LAP_RULES = (u'EC2 — BS EN 1992-1-1 (UK NA)', u'BS 8110 — legacy multiples')
_STAIR_STARTER_TYPES = (u'New foundation / beam — cast-in L bars',
                        u'Existing slab / beam — post-installed with resin')


class _ModelActionHandler(IExternalEventHandler):
    """Runs one queued window action inside Revit's API context (modeless window, D3)."""

    def __init__(self, window):
        self.window = window
        self.pending = None

    def Execute(self, uiapp):
        action, self.pending = self.pending, None
        if action is None or not self.window._same_document(uiapp):
            return
        try:
            action()
        except Exception as e:
            forms.alert(u'RebarAutomate action failed:\n{}'.format(e), title=u'RebarAutomate')

    def GetName(self):
        return u'NOSA RebarAutomate — Model Action'


# T8.5: one mixin per tab, methods unchanged
_tab_columns = load_module('ra_tab_columns', os.path.join(_HERE, 'tab_columns.py'))
_tab_beams = load_module('ra_tab_beams', os.path.join(_HERE, 'tab_beams.py'))
_tab_walls = load_module('ra_tab_walls', os.path.join(_HERE, 'tab_walls.py'))
_tab_stairs = load_module('ra_tab_stairs', os.path.join(_HERE, 'tab_stairs.py'))
_tab_tools = load_module('ra_tab_tools', os.path.join(_HERE, 'tab_tools.py'))


class RebarAutomateWindow(_tab_columns.ColumnsMixin, _tab_beams.BeamsMixin, _tab_walls.WallsMixin, _tab_stairs.StairsMixin, _tab_tools.ToolsMixin, NOSAWindow):

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
        self._model_action_handler = _ModelActionHandler(self)
        self._model_action_event = ExternalEvent.Create(self._model_action_handler)

        # Shared parameters are bound lazily by _ensure_shared_params(),
        # right before the first generation writes NOSA data: opening the
        # window never modifies the model.
        self.ra_project = rebar_project.load(self.doc)
        self.ra_generator_version = _version_mod.RA_VERSION
        self._shared_params_report = None
        self._pending_layers = {}
        self._pending_locations = {}

        # PHASE F2 — normativa (rebar standard) profile, resolved once at
        # launch and re-resolved whenever the user changes the "Standard:"
        # dropdown. self.ra_standard is the full profile dict consumed by
        # standards.cover_for/lap_length_mm/etc; self.ra_project holds the
        # persisted code string (rebar_project.json's 'standard_code').
        self.ra_standard = self._load_standard(self.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE))
        self._populate_standard_dropdown()
        self._populate_project_header()
        self._populate_detailing_combos()
        self._refresh_content_status()

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
        self._update_stair_preview()
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
        self._wire_live_previews()

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
        self._update_stair_preview()

    # ── normativa (rebar standard) — PHASE F2 ───────────────────────────

    def _ensure_shared_params(self):
        """Bind NOSA's shared parameters once per window; False if binding failed outright."""
        if self._shared_params_report is not None:
            return not self._shared_params_report.get('fatal', False)
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
        from nosa_utils.telemetry import log_info
        log_info(u'rebarautomate', u'shared parameters: {} bound, {} already, {} skipped, {} errors {}'.format(
            len(report.get('bound', [])), len(report.get('already', [])), len(report.get('skipped', [])),
            len(errors), errors[:5]))

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
        to the NOSA default (BS 8666) and finally to None (never raises) so a missing/corrupt
        user-override file under NOSA_Configs/rebar_standards/ can never
        crash the window. Every call site that consumes the result treats
        None the same as "no standard resolved" — the pre-F2 hardcoded
        defaults (DEFAULT_COVER_MM etc.) apply, matching this plugin's
        behaviour before this phase existed."""
        try:
            return standards.load(code)
        except Exception:
            if code != rebar_project.DEFAULT_STANDARD_CODE:
                try:
                    return standards.load(rebar_project.DEFAULT_STANDARD_CODE)
                except Exception:
                    log_swallowed(_LOG, u'RebarAutomateWindow._load_standard')
            return None

    def _host_std(self, host):
        """The standard profile with this host's concrete fck and the project's lap rules."""
        std = getattr(self, 'ra_standard', None)
        if std is None:
            return None
        std = dict(std)
        concrete = dict(std.get('concrete') or {})
        try:
            fck = re_engine.host_fck_mpa(self.doc, host) if host is not None else None
        except Exception:
            fck = None
        concrete['fck_mpa'] = fck or self.ra_project.get('default_fck_mpa') or \
            concrete.get('default_fck_mpa') or 32.0
        std['concrete'] = concrete
        if self.ra_project.get('lap_rules') == u'bs8110':
            std['lap'] = dict(std['lap'], mode=u'bs8110')
            std['anchorage'] = dict(std['anchorage'], mode=u'bs8110')
        return std

    def _populate_standard_dropdown(self):
        """Global "Standard:" selector (ui.xaml, outside the TabControl).
        Populated here in code from standards.list_available() — never
        XAML SelectedIndex/SelectionChanged, per the Phase 3.6 note above
        in __init__. Called BEFORE CmbStandard.SelectionChanged is wired,
        so setting SelectedItem here does not fire the handler."""
        codes = standards.list_available()
        if not codes:
            codes = [rebar_project.DEFAULT_STANDARD_CODE]
        self.CmbStandard.Items.Clear()
        for code in codes:
            self.CmbStandard.Items.Add(code)
        current_code = self.ra_project.get('standard_code', rebar_project.DEFAULT_STANDARD_CODE)
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
        self.TxtKickerHeight.Text = u'{:g}'.format(self._kicker_mm())
        self.TxtDefaultFck.Text = u'{:g}'.format(float(self.ra_project.get('default_fck_mpa') or 32.0))
        self.CmbLapRules.Items.Clear()
        for label in _LAP_RULES:
            self.CmbLapRules.Items.Add(label)
        self.CmbLapRules.SelectedIndex = 1 if self.ra_project.get('lap_rules') == u'bs8110' else 0
        self.CboStairStarterType.Items.Clear()
        for label in _STAIR_STARTER_TYPES:
            self.CboStairStarterType.Items.Add(label)
        self.CboStairStarterType.SelectedIndex = 0
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
        self.BtnExportPackage.Click += self.BtnExportPackage_Click

    def _kicker_mm(self):
        """Kicker height (mm): the value in the box, else the project setting; laps are measured above it."""
        try:
            return max(0.0, float(self.TxtKickerHeight.Text))
        except (TypeError, ValueError, AttributeError):
            log_swallowed(_LOG, u'RebarAutomateWindow._kicker_mm')
        try:
            return max(0.0, float(self.ra_project.get('kicker_mm', 75.0)))
        except (TypeError, ValueError):
            return 75.0

    def _anchorage_mm(self, host, bar_dia_mm, good_bond=True):
        """Tension anchorage for this host (lap rules, host concrete), else 40 phi."""
        try:
            return standards.anchorage_length_mm(self._host_std(host), bar_dia_mm, good_bond)
        except Exception:
            return 40.0 * bar_dia_mm

    def _partition(self):
        """The Partition as typed now (it used to take effect only after Save Project Settings)."""
        partition = (self.TxtMarkPrefix.Text or u'').strip()
        self.ra_project['mark_prefix'] = partition
        return partition

    def BtnSaveProjectHeader_Click(self, sender, args):
        """Guarda prefijo de marca, revisión y estado en rebar_project.json."""
        if not getattr(self, '_is_loaded', False):
            return
        self.ra_project['mark_prefix'] = (self.TxtMarkPrefix.Text or u'').strip()
        self.ra_project['revision'] = (self.TxtRevision.Text or u'').strip()
        self.ra_project['status'] = self.CmbProjectStatus.SelectedItem or u'Design'
        try:
            self.ra_project['kicker_mm'] = max(0.0, float(self.TxtKickerHeight.Text))
        except (TypeError, ValueError):
            forms.alert(u'Kicker height must be a number (mm).', title=u'RebarAutomate')
            return
        try:
            fck = float(self.TxtDefaultFck.Text)
            if not 12.0 <= fck <= 90.0:
                raise ValueError
            self.ra_project['default_fck_mpa'] = fck
        except (TypeError, ValueError):
            forms.alert(u'Default concrete fck must be between 12 and 90 MPa.', title=u'RebarAutomate')
            return
        self.ra_project['lap_rules'] = u'bs8110' if self.CmbLapRules.SelectedIndex == 1 else u'ec2'
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
                summary_msg += u'  H{}: {} bars, {:.2f} m, {:.1f} kg\n'.format(
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
                [u'Export to Excel (with bending sketches)', u'Export to CSV', u'Cancel'],
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
                sketches = self._bbs_sketches(schedule_data)
                success = rebar_schedule.export_xlsx(schedule_data, output_path, sketches)
            
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

    def _bbs_sketches(self, schedule_data):
        """{shape id: PNG} of the shapes the schedule uses (T7.5)."""
        from nosa_utils.revit_helpers import element_id_from_int
        shapes = []
        for shape_id in set(row.get('shape_id') for row in schedule_data if row.get('shape_id')):
            shape = self.doc.GetElement(element_id_from_int(shape_id))
            if shape is not None:
                shapes.append(shape)
        try:
            return shape_images.render_shapes(self.doc, shapes)
        except Exception as e:
            from nosa_utils.telemetry import log_info
            log_info(u'rebarautomate', u'bending sketches skipped: {}'.format(e))
            return {}

    def ShapeImages_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._in_revit(self._assign_shape_images)

    def _assign_shape_images(self):
        """T7.5 — every NOSA bar shows its shape's BS 8666 sketch; BBS schedules get the Shape column."""
        if not self._ensure_shared_params():
            return
        rebars = shape_images.nosa_rebars(self.doc)
        shapes = shape_images.shapes_of(self.doc, rebars)
        paths = shape_images.render_shapes(self.doc, shapes)
        schedules = [v for v in DB.FilteredElementCollector(self.doc).OfClass(DB.ViewSchedule)
                     if not v.IsTemplate and u'BBS' in (v.Name or u'').upper()]
        done = added = 0
        try:
            with nosa_tx.revit_transaction(u'NOSA — BS 8666 Shape Images'):
                done = shape_images.stamp_bars(self.doc, rebars, shape_images.image_types(self.doc, shapes, paths))
                for schedule in schedules:
                    if shape_images.add_shape_image_column(self.doc, schedule):
                        added += 1
        except Exception as e:
            forms.alert(u'Shape images failed:\n{}'.format(e), title=u'NOSA — Shape Images')
            return
        msg = (u'{} of {} RebarAutomate bar(s) now carry their BS 8666 sketch ({} shapes); Shape column '
               u'added to {} BBS schedule(s).'.format(done, len(rebars), len(shapes), added))
        self.TxtDetailingStatus.Text = msg
        forms.alert(msg, title=u'NOSA — Shape Images')

    def BtnExportBvbs_Click(self, sender, args):
        """Export BVBS (.abs) BF2D records for the CNC bending machine (BVBS Guideline 3.1, T4.1)."""
        if not getattr(self, '_is_loaded', False):
            return
        try:
            schedule_data = rebar_schedule.generate_schedule_data(
                self.doc, batch_id=None, include_finalized=False)
            if not schedule_data:
                forms.alert(u'No NOSA rebars found in the project.', title=u'Export BVBS')
                return

            schedule_no = forms.ask_for_string(
                default=u'1', prompt=u'Bar bending schedule / drawing number (BVBS field r):',
                title=u'Export BVBS')
            if schedule_no is None:
                return

            from System.Windows.Forms import SaveFileDialog, DialogResult
            dlg = SaveFileDialog()
            dlg.Filter = 'BVBS files (*.abs)|*.abs'
            dlg.FileName = u'{}.abs'.format(self.doc.Title or u'RebarExport')
            if dlg.ShowDialog() != DialogResult.OK:
                return
            output_path = dlg.FileName

            try:
                project_no = self.doc.ProjectInformation.Number or u''
            except Exception:
                project_no = u''
            steel_grade = ((self.ra_standard or {}).get('steel') or {}).get('default_grade', u'B500B')
            written, without_geometry = rebar_export_bvbs.export_bvbs_file(
                schedule_data, output_path, project_no=project_no, schedule_no=schedule_no,
                revision=self.ra_project.get('revision', u''), steel_grade=steel_grade)
            lines = [u'{} BVBS record(s) written ({}) to:'.format(
                         written, rebar_export_bvbs.BVBS_GUIDELINE), output_path]
            lines.append(rebar_export_bvbs.LENGTH_NOTE)
            if without_geometry:
                lines.append(u'')
                lines.append(u'{} position(s) exported without bending geometry (circular links '
                             u'or custom shapes): the fabricator bends these from the schedule.'.format(
                                 without_geometry))
            forms.alert(u'\n'.join(lines), title=u'Export Complete')
            import subprocess
            subprocess.Popen(['explorer', '/select,', output_path])
        except Exception as e:
            forms.alert(u'BVBS export failed:\n{}'.format(e), title=u'Error', warn_icon=True)

    def BtnExportPackage_Click(self, sender, args):
        """T7.10 — one folder for the fabricator: BBS (Excel with sketches + CSV) and the BVBS file."""
        if not getattr(self, '_is_loaded', False):
            return
        try:
            schedule_data = rebar_schedule.generate_schedule_data(
                self.doc, batch_id=None, include_finalized=False)
            if not schedule_data:
                forms.alert(u'No NOSA rebars found in the project.', title=u'Fabrication Package')
                return
            schedule_no = forms.ask_for_string(
                default=u'1', prompt=u'Bar bending schedule / drawing number:', title=u'Fabrication Package')
            if schedule_no is None:
                return
            from System.Windows.Forms import FolderBrowserDialog, DialogResult
            dlg = FolderBrowserDialog()
            dlg.Description = u'Folder for the BBS and BVBS files'
            if dlg.ShowDialog() != DialogResult.OK:
                return
            files, notes = self._write_fabrication_package(schedule_data, dlg.SelectedPath, schedule_no)
            forms.alert(u'\n'.join([u'Fabrication package written:'] + files + notes), title=u'Export Complete')
            import subprocess
            subprocess.Popen(['explorer', dlg.SelectedPath])
        except Exception as e:
            forms.alert(u'Fabrication package failed:\n{}'.format(e), title=u'Error', warn_icon=True)

    def _write_fabrication_package(self, schedule_data, folder, schedule_no):
        """Write <title>_BBS.xlsx, <title>_BBS.csv and <title>.abs to folder -> (paths, notes)."""
        base = re.sub(r'[\\/:*?"<>|]', u'_', self.doc.Title or u'Rebar')
        files, notes = [], []
        xlsx = os.path.join(folder, u'{}_BBS.xlsx'.format(base))
        if rebar_schedule.export_xlsx(schedule_data, xlsx, self._bbs_sketches(schedule_data)):
            files.append(xlsx)
        csv_path = os.path.join(folder, u'{}_BBS.csv'.format(base))
        if rebar_schedule.export_csv(schedule_data, csv_path):
            files.append(csv_path)
        try:
            project_no = self.doc.ProjectInformation.Number or u''
        except Exception:
            project_no = u''
        steel_grade = ((self.ra_standard or {}).get('steel') or {}).get('default_grade', u'B500B')
        abs_path = os.path.join(folder, u'{}.abs'.format(base))
        written, without_geometry = rebar_export_bvbs.export_bvbs_file(
            schedule_data, abs_path, project_no=project_no, schedule_no=schedule_no,
            revision=self.ra_project.get('revision', u''), steel_grade=steel_grade)
        files.append(abs_path)
        notes.append(u'{} BVBS record(s) ({}).'.format(written, rebar_export_bvbs.BVBS_GUIDELINE))
        notes.append(rebar_export_bvbs.LENGTH_NOTE)
        if without_geometry:
            notes.append(u'{} position(s) without bending geometry: the fabricator bends these from '
                         u'the schedule.'.format(without_geometry))
        return files, notes

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
        self._update_preview()

    def IncludeDowels_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelDowels.IsEnabled = self.ChkIncludeDowels.IsChecked == True
        self._update_preview()

    def IncludePerimeterUBars_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelPerimeterUBars.IsEnabled = self.ChkIncludePerimeterUBars.IsChecked == True
        self._update_preview()

    def IncludeOpeningDiagonals_Click(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self.PanelOpeningDiagonals.IsEnabled = self.ChkOpeningDiagonals.IsChecked == True

    # ── section preview (Phase 2) ────────────────────────────────────────
    # Recomputed and redrawn on every keystroke in a cover/diameter/
    # spacing field, or when Top Mat is toggled — never touches the Revit
    # document (rebar_preview.compute_section_preview is pure Python), so
    # this stays cheap even on a fast typist. Invalid/incomplete input
    # mid-typing is handled by simply skipping the redraw (not erroring
    # the user) until the fields parse again.

    def _wire_live_previews(self):
        """Every check box, text box and combo box of a tab refreshes that tab's preview at once."""
        from System.Windows import LogicalTreeHelper, DependencyObject
        handlers = (self.Preview_Changed, self.ColumnPreview_Changed,
                    self.BeamPreview_Changed, self.WallPreview_Changed, self.StairPreview_Changed)

        def descendants(node):
            for child in LogicalTreeHelper.GetChildren(node):
                if isinstance(child, DependencyObject):
                    yield child
                    for grandchild in descendants(child):
                        yield grandchild

        for index, handler in enumerate(handlers):
            if index >= self.MainTabControl.Items.Count:
                break
            for control in descendants(self.MainTabControl.Items[index]):
                if isinstance(control, SWC.CheckBox):
                    control.Click += handler
                elif isinstance(control, SWC.TextBox):
                    control.TextChanged += handler
                elif isinstance(control, SWC.ComboBox):
                    control.SelectionChanged += handler
        self.TxtKickerHeight.TextChanged += self._all_previews_changed

    def _all_previews_changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._update_preview()
        self._update_column_preview()
        self._update_beam_preview()
        self._update_wall_preview()
        self._update_stair_preview()

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

        self._draw_shapes(self.PreviewCanvas, self._mat_preview_shapes(
            preview_host, preview_kind, cover, dia_x, dia_y, include_top, top_cover,
            top_dia_x, top_dia_y, include_ubars, x_anchor_dia, bottom_hooks, top_hooks))
        self._update_adopted_solution_label(cover, dia_x, dia_y, include_top,
                                            top_cover, top_dia_x, top_dia_y,
                                            include_ubars)

    def _preview_number(self, box, default):
        """Float from a text box for the previews; the default if empty or invalid."""
        try:
            value = float(box.Text)
            return value if value > 0 else default
        except (TypeError, ValueError, AttributeError):
            return default

    def _mat_preview_shapes(self, host, kind, cover, dia_x, dia_y, include_top, top_cover,
                            top_dia_x, top_dia_y, include_ubars, ubar_dia, bottom_hooks, top_hooks):
        """Section through the selected footing/slab (or a typical one) with every active option."""
        width_mm, thickness_mm = (1500.0, 500.0) if kind != u'slab' else (3000.0, 300.0)
        if host is not None:
            try:
                bbox = re_engine.get_isolated_solid_bbox(host) or host.get_BoundingBox(None)
                width_mm = min((bbox.Max.X - bbox.Min.X) * 304.8, 4000.0)
                thickness_mm = (bbox.Max.Z - bbox.Min.Z) * 304.8
            except Exception:
                log_swallowed(_LOG, u'RebarAutomateWindow._mat_preview_shapes')
        spacing = self._preview_number(self.TxtSpacing, 200.0)
        dowels = kind != u'slab' and self.ChkIncludeDowels.IsChecked == True
        return preview_shapes.mat_section_shapes(
            width_mm, thickness_mm, cover, dia_x, dia_y, spacing,
            include_top=include_top, top_cover_mm=top_cover, top_dia_x=top_dia_x,
            top_dia_y=top_dia_y, top_spacing_mm=self._preview_number(self.TxtTopSpacing, spacing),
            ubars=include_ubars, ubar_dia=ubar_dia, is_floor=kind == u'slab',
            bottom_hooks=bottom_hooks, top_hooks=top_hooks, dowels=dowels,
            dowel_dia=self._preview_number(self.TxtDowelDiameter, 16.0),
            dowel_splice_mm=self._preview_splice(
                self.TxtDowelSplice, self._preview_number(self.TxtDowelDiameter, 16.0)),
            kicker_mm=self._kicker_mm(),
            column_width_mm=self._preview_number(self.TxtDowelColWidth, 400.0),
            side=kind != u'slab' and self.ChkIncludeSideRebar.IsChecked == True,
            side_dia=self._preview_number(self.TxtSideDiameter, 10.0),
            side_spacing_mm=self._preview_number(self.TxtSideSpacing, 300.0))

    def _draw_shapes(self, canvas, shapes):
        """Draw rebar_preview_shapes output (real mm, y up) fitted to the canvas, labels on the right."""
        canvas.Children.Clear()
        geo = [sh for sh in shapes if sh['kind'] != 'text']
        xs, ys = [], []
        for sh in geo:
            if sh['kind'] in ('concrete', 'ground', 'ghost_column'):
                xs += [sh['x0'], sh['x1']]
                ys += [sh['y0'], sh['y1']]
            elif sh['kind'] == 'circle':
                xs += [sh['x'] - sh['r'], sh['x'] + sh['r']]
                ys += [sh['y'] - sh['r'], sh['y'] + sh['r']]
            elif sh['kind'] == 'bar':
                xs += [p[0] for p in sh['points']]
                ys += [p[1] for p in sh['points']]
            elif sh['kind'] == 'dot':
                xs.append(sh['x'])
                ys.append(sh['y'])
            elif sh['kind'] == 'level':
                xs += [sh['x0'], sh['x1']]
                ys.append(sh['y'])
            elif sh['kind'] == 'outline':
                xs += [p[0] for p in sh['points']]
                ys += [p[1] for p in sh['points']]
        if not xs:
            return
        texts = [sh for sh in shapes if sh['kind'] == 'text']
        cw, ch, margin, row = canvas.Width, canvas.Height, 12.0, 14.0
        label_px = 6.2 * max([len(t['text']) for t in texts] or [0]) + 10.0
        below = label_px > 0.4 * cw
        label_h = row * len(texts) + 4.0 if below else 0.0
        if below:
            label_px = 0.0
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        scale = min((cw - 2 * margin - label_px) / max(x1 - x0, 1.0),
                    (ch - 2 * margin - label_h) / max(y1 - y0, 1.0))
        off_x = margin + (cw - 2 * margin - label_px - (x1 - x0) * scale) / 2.0
        off_y = margin + (ch - 2 * margin - label_h - (y1 - y0) * scale) / 2.0

        def sx(x):
            return off_x + (x - x0) * scale

        def sy(y):
            return off_y + (y1 - y) * scale

        colours = {'main': _PREVIEW_BAR_FILL, 'link': SolidColorBrush(Color.FromRgb(110, 110, 110)),
                   'ubar': SolidColorBrush(Color.FromRgb(150, 75, 20)),
                   'starter': _PREVIEW_SECTION_STROKE, 'dowel': _PREVIEW_SECTION_STROKE,
                   'ghost': SolidColorBrush(Color.FromRgb(160, 160, 160))}
        for sh in geo:
            kind = sh['kind']
            if kind in ('concrete', 'ground', 'ghost_column'):
                rect = SWS.Rectangle()
                rect.Width = max(1.0, (sh['x1'] - sh['x0']) * scale)
                rect.Height = max(1.0, (sh['y1'] - sh['y0']) * scale)
                if kind == 'concrete':
                    rect.Stroke, rect.Fill = _PREVIEW_SECTION_STROKE, _PREVIEW_SECTION_FILL
                elif kind == 'ground':
                    rect.Stroke = colours['ghost']
                    rect.Fill = SolidColorBrush(Color.FromArgb(40, 128, 128, 128))
                else:
                    rect.Stroke = colours['ghost']
                    rect.StrokeDashArray = SWM.DoubleCollection([4.0, 3.0])
                rect.StrokeThickness = 1.2
                SWC.Canvas.SetLeft(rect, sx(sh['x0']))
                SWC.Canvas.SetTop(rect, sy(sh['y1']))
                canvas.Children.Add(rect)
            elif kind == 'outline':
                poly = SWS.Polygon()
                for x, y in sh['points']:
                    poly.Points.Add(System.Windows.Point(sx(x), sy(y)))
                poly.Stroke, poly.Fill = _PREVIEW_SECTION_STROKE, _PREVIEW_SECTION_FILL
                poly.StrokeThickness = 1.2
                canvas.Children.Add(poly)
            elif kind == 'circle':
                ell = SWS.Ellipse()
                ell.Width = ell.Height = 2 * sh['r'] * scale
                ell.Stroke, ell.Fill = _PREVIEW_SECTION_STROKE, _PREVIEW_SECTION_FILL
                ell.StrokeThickness = 1.2
                SWC.Canvas.SetLeft(ell, sx(sh['x'] - sh['r']))
                SWC.Canvas.SetTop(ell, sy(sh['y'] + sh['r']))
                canvas.Children.Add(ell)
            elif kind == 'bar':
                line = SWS.Polyline()
                for x, y in sh['points']:
                    line.Points.Add(System.Windows.Point(sx(x), sy(y)))
                line.Stroke = colours.get(sh['role'], _PREVIEW_BAR_FILL)
                line.StrokeThickness = max(1.2, sh['dia_mm'] * scale)
                line.StrokeLineJoin = SWM.PenLineJoin.Round
                canvas.Children.Add(line)
            elif kind == 'dot':
                d = max(4.0, sh['dia_mm'] * scale)
                ell = SWS.Ellipse()
                ell.Width = ell.Height = d
                brush = colours.get(sh['role'], _PREVIEW_BAR_FILL)
                if sh.get('hollow'):
                    ell.Stroke, ell.StrokeThickness = brush, 1.5
                else:
                    ell.Fill = brush
                SWC.Canvas.SetLeft(ell, sx(sh['x']) - d / 2.0)
                SWC.Canvas.SetTop(ell, sy(sh['y']) - d / 2.0)
                canvas.Children.Add(ell)
            elif kind == 'level':
                line = SWS.Line()
                line.X1, line.Y1, line.X2, line.Y2 = sx(sh['x0']), sy(sh['y']), sx(sh['x1']), sy(sh['y'])
                line.Stroke = colours['ghost']
                line.StrokeDashArray = SWM.DoubleCollection([6.0, 4.0])
                canvas.Children.Add(line)
        placed = []
        if below:
            top = ch - margin - label_h + 4.0
            for i, t in enumerate(sorted(texts, key=lambda t: -t['y'])):
                placed.append((t, margin, top + i * row))
        else:
            last = -row
            for t in sorted(texts, key=lambda t: -t['y']):
                y = max(sy(t['y']) - 7.0, last + row)
                last = y
                placed.append((t, sx(x1) + 8.0 if t['x'] >= x1 else sx(t['x']), min(y, ch - row)))
        for t, left, y in placed:
            tb = SWC.TextBlock()
            tb.Text = t['text']
            tb.FontSize = 10.5
            tb.SetResourceReference(SWC.TextBlock.ForegroundProperty, 'TextColor')
            SWC.Canvas.SetLeft(tb, left)
            SWC.Canvas.SetTop(tb, y)
            canvas.Children.Add(tb)

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

    def _read_splice(self, text, label, errors):
        """'Auto' (or blank / 0) -> None: the lap is computed per host; otherwise a length in mm."""
        if (text or u'').strip().lower() in (u'', u'auto', u'0'):
            return None
        return self._read_number(text, label, errors)

    def _splice_mm(self, typed_mm, bar_dia_mm, host, errors=None, label=u'Splice'):
        """Starter / dowel lap: typed length, else l0 for this host; never below max(15 phi, 300 mm)."""
        floor_mm = max(15.0 * bar_dia_mm, 300.0)
        if typed_mm is None:
            try:
                return standards.lap_length_mm(self._host_std(host), bar_dia_mm, False, 100.0, True)
            except Exception:
                return max(40.0 * bar_dia_mm, floor_mm)
        if typed_mm < floor_mm and errors is not None:
            errors.append(u'{} {:.0f} mm raised to {:.0f} mm: no lap may be shorter than '
                          u'max(15 bar diameters, 300 mm).'.format(label, typed_mm, floor_mm))
        return max(typed_mm, floor_mm)

    def _preview_splice(self, textbox, bar_dia_mm):
        """Preview lap: the typed length, else l0 with the project concrete."""
        typed = None
        try:
            if (textbox.Text or u'').strip().lower() not in (u'', u'auto', u'0'):
                typed = float(textbox.Text)
        except (TypeError, ValueError):
            typed = None
        return self._splice_mm(typed, bar_dia_mm, None)

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
            values['dowel_splice'] = self._read_splice(
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
                # A dowel laps with a column vertical: same diameter (user decision 2026-10-01).
                values['dowel_diameter'] = values['dowel_col_bar_dia']
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

        values['include_opening_diagonals'] = self.ChkOpeningDiagonals.IsChecked == True
        values['corner_torsion'] = self.ChkCornerTorsion.IsChecked == True
        values['top_over_supports'] = self.ChkTopOverSupports.IsChecked == True
        if values['include_opening_diagonals']:
            values['opening_diagonal_dia'] = self._read_number(
                self.TxtOpeningDiagonalDia.Text, u'Opening corner diagonal bar diameter', errors)

        values['generate_sections'] = self.ChkGenerateSections.IsChecked == True
        values['stagger_laps'] = self.ChkStaggerLaps.IsChecked == True

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
        if values.get('include_opening_diagonals'):
            diameters.add(values['opening_diagonal_dia'])

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
        bar_dia_mm = bar_type.BarModelDiameter * 304.8
        cover_mm = re_engine.get_native_cover_mm(self.doc, host, u'Exterior', 40.0)
        short_feet = []
        for line, normal in zip(dowels['bars'], dowels['normals']):
            curves, foot_mm = re_engine.starter_l_curves(
                line, normal.CrossProduct(DB.XYZ.BasisZ), bar_dia_mm, host, cover_mm)
            if foot_mm < re_engine.MIN_STARTER_FOOT_MM - 1.0:
                short_feet.append(foot_mm)
            rebar = wrapper.create_from_curves(
                host, curves, bar_type, normal=normal,
                transaction_name=u'NOSA — Create Footing Dowel')
            if rebar is None:
                errors.append(u'Footing {}: dowel — {}'.format(get_id_value(host.Id), wrapper.last_error))
            else:
                self._stamp_layer(rebar, u'dowel')
                created_rebars.append(rebar)
        self._create_starter_links(
            wrapper, [dict(g, foundation=host) for g in dowels.get('groups', [])], bar_dia_mm, cover_mm,
            errors, created_rebars, u'Footing', host)
        if short_feet:
            errors.append(u'Footing {}: {} dowel foot/feet shortened to {:.0f} mm to stay inside the '
                          u'footing (450 mm recommended).'.format(
                              get_id_value(host.Id), len(short_feet), min(short_feet)))
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

    def _create_starter_links(self, wrapper, groups, bar_dia_mm, cover_mm, errors, created_rebars,
                              label, host):
        """IStructE SMDSC MF1 / MC1: H10-300 links (3 at least) round each rectangular cage of starters."""
        from nosa_utils import links
        if not groups:
            return
        bar_type = re_engine.get_bar_type_by_diameter(self.doc, links.STARTER_LINK_DIA_MM)
        if bar_type is None:
            errors.append(u'{} {}: no H10 bar type in the project — starter links (SMDSC MF1) '
                          u'not created.'.format(label, get_id_value(host.Id)))
            return
        skipped = 0
        for group in groups:
            top_cover = re_engine.get_native_cover_mm(self.doc, group['foundation'], u'Top', cover_mm)
            link_set = re_engine.starter_link_set(group['bars'], group['hand'], group['foundation'],
                                                  links.STARTER_LINK_DIA_MM, bar_dia_mm, top_cover)
            if link_set is None:
                skipped += 1
                continue
            self._create_grouped_bars(wrapper, group['foundation'], {'sets': [link_set], 'bars': []},
                                      bar_type, errors, created_rebars, u'Starter Link',
                                      layer=u'starter_link')
        if skipped:
            errors.append(u'{} {}: {} starter cage(s) without links — not rectangular or no room in '
                          u'the foundation; add H10-300 (3 at least, SMDSC MF1) by hand.'.format(
                              label, get_id_value(host.Id), skipped))

    def _foundation_starter_mm(self, typed_mm, bar_dia_mm, host, errors, min_kicker_mm=0.0):
        """Foundation starter projection (SMDSC MF1 / MC1 / MW1): lap + kicker + 150 level tolerance."""
        try:
            base_ft = host.get_BoundingBox(None).Min.Z
        except Exception:
            base_ft = None
        return (self._splice_mm(typed_mm, bar_dia_mm, host, errors, u'Starter splice')
                + max(self._kicker_at_mm(base_ft, host, errors), min_kicker_mm)
                + standards.FOUNDATION_LEVEL_TOLERANCE_MM)

    def _ground_level_ft(self):
        """Elevation of the project's ground level: the level named 'Ground…', else 0."""
        try:
            for level in DB.FilteredElementCollector(self.doc).OfClass(DB.Level):
                if level.Name.lower().startswith(u'ground'):
                    return level.Elevation
        except Exception:
            log_swallowed(_LOG, u'RebarAutomateWindow._ground_level_ft')
        return 0.0

    def _kicker_at_mm(self, base_ft, host, errors):
        """Kicker height at a base: the set one, at least 150 mm below ground (SMDSC MF1 / MC1 / MW1)."""
        kicker = self._kicker_mm()
        if base_ft is None or kicker >= 150.0 or base_ft >= self._ground_level_ft() - 50.0 / 304.8:
            return kicker
        errors.append(u'{} {}: base below ground — kicker 150 mm (SMDSC MF1 / MW1), not {:.0f}.'.format(
            host.Category.Name if host.Category else u'Element', get_id_value(host.Id), kicker))
        return 150.0

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
        bar_dia_mm = bar_type.BarModelDiameter * 304.8
        short_feet = []
        for line, normal, foundation in zip(starters.get('bars', []), starters.get('normals', []),
                                            starters.get('hosts', [])):
            curves, foot_mm = re_engine.starter_l_curves(
                line, normal.CrossProduct(DB.XYZ.BasisZ), bar_dia_mm, foundation,
                re_engine.get_native_cover_mm(self.doc, foundation, u'Exterior', 40.0))
            if foot_mm < re_engine.MIN_STARTER_FOOT_MM - 1.0:
                short_feet.append(foot_mm)
            rebar = wrapper.create_from_curves(
                foundation, curves, bar_type, normal=normal,
                transaction_name=u'NOSA — Create {} Foundation Starter'.format(label))
            if rebar is None:
                errors.append(u'{} {}: foundation starter — {}'.format(
                    label, get_id_value(host.Id), wrapper.last_error))
            else:
                self._stamp_layer(rebar, u'foundation_starter')
                created_rebars.append(rebar)
        if short_feet:
            errors.append(u'{} {}: {} starter foot/feet shortened to {:.0f} mm to stay inside the '
                          u'foundation (450 mm recommended).'.format(
                              label, get_id_value(host.Id), len(short_feet), min(short_feet)))
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

    def _stamp_location(self, rebar, location):
        """Record a label location code (N1/N2/F1/F2) that the layer alone cannot tell."""
        if rebar is not None and location:
            self._pending_locations[get_id_value(rebar.Id)] = location

    @staticmethod
    def _set_runs_along_its_plane(group):
        """True when a set's distribution normal is not square to the plane of its bar."""
        try:
            curves = group['curves']
            chain = [(p.X, p.Y, p.Z) for p in [curves[0].GetEndPoint(0)] + [c.GetEndPoint(1) for c in curves]]
            plane = varying_sets.plane_normal(chain)
            if plane is None:
                return False
            n = group['normal']
            return abs(plane[0] * n.X + plane[1] * n.Y + plane[2] * n.Z) < 0.999
        except Exception:
            return False

    def _create_varying_runs(self, wrapper, host, bars, bar_type, style, label, layer, created_rebars):
        """Varying rebar sets for the runs of `bars` one set can hold; returns the bars left over."""
        chains = [[(p.X * 304.8, p.Y * 304.8, p.Z * 304.8)
                   for p in [b['curves'][0].GetEndPoint(0)] + [c.GetEndPoint(1) for c in b['curves']]]
                  for b in bars]
        left = []
        for run in varying_sets.split_runs(chains):
            if len(run) < 2:
                left.extend(bars[i] for i in run)
                continue
            # rows are trimmed to whole 25 mm lengths (floor_rebar.trim_to_step_mm): a set that
            # follows the faces sits up to one step off them; half a step inside keeps the cover
            rebar = wrapper.create_varying_set(
                host, [bars[i]['curves'] for i in run], bar_type, style=style,
                transaction_name=u'NOSA — Create {} (varying set)'.format(label),
                tolerance_mm=VARYING_STEP_TOLERANCE_MM, end_margin_mm=VARYING_END_MARGIN_MM)
            if rebar is None:
                from nosa_utils.telemetry import log_info
                log_info(u'rebarautomate', u'{}: varying set not built ({}); FreeForm instead'.format(
                    label, wrapper.last_error))
                left.extend(bars[i] for i in run)
                continue
            self._stamp_layer(rebar, layer)
            created_rebars.append(rebar)
        return left

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

        2026-10-05 (user decision): before FreeForm, rows cut by an
        inclined face become Revit varying rebar sets (one element per
        run, MRA-taggable, real shape code, every bar its own length as a
        sub-mark in the BBS); FreeForm is left for what no varying set
        can follow.
        """
        errors.extend(grouped.get('notes') or [])
        if bar_type is None:
            return
        style_map = {'StirrupTie': DBS.RebarStyle.StirrupTie}
        for s in grouped.get('sets', []):
            style = style_map.get(s.get('style'))
            if self._set_runs_along_its_plane(s):
                # rows stepping along an inclined edge: no Rebar Set can hold them (Revit throws
                # "An internal error has occurred"), straight to the varying set below
                rebar = None
                wrapper.last_error = u'rows step along an inclined edge'
            else:
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
                    with nosa_tx.revit_transaction(u'NOSA — Remove Unpropagated Bar'):
                        self.doc.Delete(rebar.Id)
                except Exception:
                    log_swallowed(_LOG, u'RebarAutomateWindow._create_grouped_bars')

            materialized = s.get('materialized_bars', [])
            if len(materialized) >= 2:
                # 2026-10-05: rows Revit cannot propagate (bars along an inclined edge) become
                # varying sets whose ends follow the faces; FreeForm only for what is left
                materialized = self._create_varying_runs(
                    wrapper, host, materialized, bar_type, style, label, layer, created_rebars)
                if not materialized:
                    continue
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
        if len(freeform_candidates) >= 2:
            # bars cut by a chamfer: one varying set per run, real lengths per bar in the BBS
            freeform_candidates = self._create_varying_runs(
                wrapper, host, freeform_candidates, bar_type, None, label, layer, created_rebars)
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
        with nosa_tx.revit_transaction(u'NOSA — Footing Detail Sections'):
            for host in footings:
                for axis in ('X', 'Y'):
                    section = rebar_detailing.create_rebar_detail_section(
                        self.doc, host, vft.Id, cut_axis=axis)
                    if section is None:
                        errors.append(u'Footing {}: could not create the {}-axis '
                                      u'detail section.'.format(get_id_value(host.Id), axis))
                    else:
                        rebar_views.ensure_fine(section)
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
        values = self._smdsc_mesh_review(host, values, bottom_cover_mm, top_cover_mm, errors, foundation=True)
        values = self._pile_cap_values(host, values, bar_types, errors)
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
            dowel_splice_length_mm=self._splice_mm(
                values.get('dowel_splice'), values.get('dowel_diameter') or 16.0, host, errors,
                u'Dowel splice') + self._kicker_at_mm(footing_rebar._footing_bbox(host).Max.Z, host, errors)
            + standards.FOUNDATION_LEVEL_TOLERANCE_MM,
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
            std=self._host_std(host))
        if self._is_pile_cap(host):
            side_cover_mm = re_engine.get_native_cover_mm(self.doc, host, u'Exterior', bottom_cover_mm)
            errors.extend(u'Pile cap {}: {}'.format(get_id_value(host.Id), n)
                          for n in footing_rebar.pile_cap_anchorage_notes(
                              host, side_cover_mm, bottom_cover_mm, top_cover_mm, values['dia_x'], values['dia_y'],
                              self._anchorage_mm(host, values['dia_x']), self._anchorage_mm(host, values['dia_y'])))

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

    def _is_pile_cap(self, host):
        try:
            return u'pile' in host.Symbol.FamilyName.lower() or bool(footing_rebar.pile_centres_ft(host))
        except Exception:
            return False

    def _pile_cap_values(self, host, values, bar_types, errors):
        """IStructE SMDSC MF2 / Table 6.10: main bars bent at both ends, two layers of H12 lacers."""
        if not self._is_pile_cap(host):
            return values
        label = u'Pile cap {}'.format(get_id_value(host.Id))
        if not values.get('bottom_hooks'):
            values = dict(values, bottom_hooks=True)
            errors.append(u'{}: main bars bent up at both ends (SMDSC MF2, Table 6.10).'.format(label))
        if not values.get('include_side_rebar'):
            values = dict(values, include_side_rebar=True, side_diameter=12.0, side_spacing=10000.0)
            if bar_types.get(12.0) is None:
                bar_types[12.0] = re_engine.get_bar_type_by_diameter(self.doc, 12.0)
            errors.append(u'{}: two layers of H12 lacers added (SMDSC MF2).'.format(label))
        return values

    def _smdsc_mesh_review(self, host, values, bottom_cover_mm, top_cover_mm, errors, foundation):
        """
        T8.39/T8.41 — IStructE SMDSC 6.2 (slabs) / 6.7 (foundations) for this host's mats: pitches
        over the maxima come down (values copied, never the shared dict), the rest is reported.
        """
        try:
            from nosa_utils import mesh_rules, standards
            # the structural layers of a layered type (a foundation slab carries blinding and
            # hardcore layers that are no concrete to reinforce), else the host's own solid
            h_mm = 0.0
            try:
                structure = self.doc.GetElement(host.GetTypeId()).GetCompoundStructure()
                h_mm = sum(layer.Width for layer in structure.GetLayers()
                           if layer.Function == DB.MaterialFunctionAssignment.Structure) * 304.8
            except Exception:
                h_mm = 0.0
            if h_mm <= 0.0:
                box = re_engine.get_isolated_solid_bbox(host) or host.get_BoundingBox(None)
                h_mm = (box.Max.Z - box.Min.Z) * 304.8
            try:
                fck = standards.concrete_fck_mpa(self._host_std(host))
            except Exception:
                fck = 30.0
            top = None
            if values.get('include_top_mat'):
                top = (values['top_dia_x'], values['top_dia_y'], values['top_spacing'], top_cover_mm)
            label = u'{} {}'.format(u'Foundation' if foundation else u'Slab', get_id_value(host.Id))
            if foundation:
                name = u''
                try:
                    name = host.Symbol.FamilyName.lower()
                except Exception:
                    name = u''
                spacing, top_spacing, notes = mesh_rules.foundation_review(
                    h_mm, bottom_cover_mm, values['dia_x'], values['dia_y'], values['spacing'], fck, top=top,
                    piled=u'pile' in name, label=label)
            else:
                spacing, top_spacing, notes = mesh_rules.slab_review(
                    h_mm, bottom_cover_mm, values['dia_x'], values['dia_y'], values['spacing'], fck, top=top,
                    label=label)
            errors.extend(notes)
            if spacing != values['spacing'] or (top and top_spacing != values['top_spacing']):
                values = dict(values, spacing=spacing)
                if top:
                    values['top_spacing'] = top_spacing
            if not foundation and values.get('include_perimeter_ubars'):
                # SMDSC MS2: the edge U-bars carry half the area of the bottom bars they close
                for axis in (u'x', u'y'):
                    key, sp_key = u'{}_anchor_ubar_dia'.format(axis), u'{}_anchor_ubar_spacing'.format(axis)
                    if not values.get(key) or not values.get(sp_key):
                        continue
                    need = mesh_rules.edge_ubar_dia_mm(values[key], values[sp_key], values[u'dia_' + axis],
                                                       values['spacing'])
                    if need > values[key]:
                        errors.append(u'{}: {} edge U-bars H{:g} raised to H{:g} — SMDSC MS2 asks for half the '
                                      u'area of the bottom bars (H{:g} at {:g}).'.format(
                                          label, axis.upper(), values[key], need, values[u'dia_' + axis],
                                          values['spacing']))
                        values = dict(values, **{key: need})
        except Exception:
            log_swallowed(_LOG, u'RebarAutomateWindow._smdsc_mesh_review')
        return values

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
        values = self._smdsc_mesh_review(host, values, bottom_cover_mm, top_cover_mm, errors, foundation=False)
        for dia in (values.get('x_anchor_ubar_dia'), values.get('y_anchor_ubar_dia')):
            if dia and bar_types.get(dia) is None:
                bar_types[dia] = re_engine.get_bar_type_by_diameter(self.doc, dia)
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
            std=self._host_std(host),
            include_opening_diagonals=values.get('include_opening_diagonals', False),
            opening_diagonal_dia_mm=values.get('opening_diagonal_dia'),
            stagger_laps=values.get('stagger_laps', False),
            corner_torsion=values.get('corner_torsion', False),
            top_over_supports=values.get('top_over_supports', False))

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

        diagonals = reinforcement.get('opening_diagonals')
        if diagonals is not None:
            diagonal_type = bar_types.get(values.get('opening_diagonal_dia'))
            for mat, layer in (('bottom', u'diagonal_bottom'), ('top', u'diagonal_top')):
                if diagonals.get(mat) is not None:
                    self._create_grouped_bars(
                        wrapper, host, diagonals[mat], diagonal_type, errors, created_rebars,
                        u'Floor Opening Corner Diagonal ({})'.format(mat.capitalize()),
                        layer=layer)
            if diagonals.get('n_skipped'):
                errors.append(u'Floor {}: {} opening corner(s) too close to an edge or another '
                              u'opening for a 45° diagonal bar — detail by hand.'.format(
                                  get_id_value(host.Id), diagonals['n_skipped']))

        for layer, dia, grouped in reinforcement.get('corner_torsion') or []:
            if bar_types.get(dia) is None:
                bar_types[dia] = re_engine.get_bar_type_by_diameter(self.doc, dia)
            self._create_grouped_bars(
                wrapper, host, grouped, bar_types.get(dia), errors, created_rebars,
                u'Floor Corner Torsion Bar', layer=layer)
        errors.extend(u'Floor {}: {}'.format(get_id_value(host.Id), n)
                      for n in (reinforcement.get('torsion_notes') or []) + (reinforcement.get('top_notes') or []))
        for layer, dia, grouped in reinforcement.get('hole_trimmers') or []:
            if bar_types.get(dia) is None:
                bar_types[dia] = re_engine.get_bar_type_by_diameter(self.doc, dia)
            self._create_grouped_bars(
                wrapper, host, grouped, bar_types.get(dia), errors, created_rebars,
                u'Floor Opening Trimmer', layer=layer)
        errors.extend(u'Floor {}: {}'.format(get_id_value(host.Id), n)
                      for n in reinforcement.get('hole_notes') or [])

        if reinforcement.get('n_small_holes_ignored'):
            errors.append(u'Floor {}: {} small opening(s) (sides ≤ 150 mm, SMDSC 6.2) ignored — '
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
            if is_ground_beam(host):
                errors.append(u'Footing {}: a ground beam — reinforce it from the Beams tab.'.format(
                    get_id_value(host.Id)))
                continue
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
                log_swallowed(_LOG, u'RebarAutomateWindow._run_reinforcement')
            if skip_reason is not None:
                errors.append(u'Tagging skipped for all {} bar(s) — {}'.format(
                    len(created_rebars), skip_reason))
            else:
                try:
                    with nosa_tx.revit_transaction(u'NOSA — Tag Rebar'):
                        tags, tag_errors = rebar_detailing.create_rebar_tags(
                            self.doc, view, created_rebars,
                            tag_type_id=rebar_detailing.tag_type_for_view(self.doc, view))
                        rebar_detailing.resolve_tag_overlaps(self.doc, view, tags)
                    tags_created = len(tags)
                    errors.extend(tag_errors)
                except Exception as e:
                    errors.append(u'Tagging failed: {}'.format(e))

        sections_created = 0
        if values['generate_sections'] and footings:
            sections_created = self._create_detail_sections(footings, errors)

        return created_rebars, {'created': created, 'tags': tags_created,
                                 'sections': sections_created, 'errors': errors}

    # ── shared ────────────────────────────────────────────────────────────

    def Theme_Toggled(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)


# the tab modules use the same shared names as this module
for _tab in (_tab_columns, _tab_beams, _tab_walls, _tab_stairs, _tab_tools,):
    _tab.bind(globals())
