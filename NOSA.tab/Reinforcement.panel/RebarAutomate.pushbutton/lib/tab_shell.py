# -*- coding: utf-8 -*-
"""
NOSA.RebarAutomate — window shell (Phase 10): side navigation, selection bar, one GENERATE in the action bar,
next step, QA badge, inline checks of the number fields, reset to defaults, the last tab remembered and the
options that do not apply to the selection hidden. The pure parts are plain functions (tested in CPython).
"""
try:
    unicode
except NameError:
    unicode = str  # CPython 3 compat


def bind(namespace):
    """Share ui.py's module-level names (modules, helpers, constants) with this module."""
    own = _OWN
    for key, value in namespace.items():
        if not key.startswith('__') and key not in own:
            globals()[key] = value


# (tab, its GENERATE handler, its run log)
ELEMENT_TABS = (('TabSlabs', 'RunReinforcement_Click', 'TxtResult'),
                ('TabBases', 'RunReinforcement_Click', 'TxtResult'),
                ('TabColumns', 'RunColumnReinforcement_Click', 'TxtColumnResult'),
                ('TabBeams', 'RunBeamReinforcement_Click', 'TxtBeamResult'),
                ('TabWalls', 'RunWallReinforcement_Click', 'TxtWallResult'),
                ('TabStairs', 'RunStairReinforcement_Click', 'TxtStairResult'))
DEFAULT_BUTTONS = (('BtnDefaultsSlabs', 'TabSlabs'), ('BtnDefaultsColumns', 'TabColumns'),
                   ('BtnDefaultsBeams', 'TabBeams'), ('BtnDefaultsWalls', 'TabWalls'),
                   ('BtnDefaultsStairs', 'TabStairs'))
# selection kind -> (tab, singular, plural)
KINDS = (('slab', 'TabSlabs', u'slab', u'slabs'), ('base', 'TabBases', u'base', u'bases'),
         ('column', 'TabColumns', u'column', u'columns'), ('beam', 'TabBeams', u'beam', u'beams'),
         ('wall', 'TabWalls', u'wall', u'walls'), ('stair', 'TabStairs', u'stair', u'stairs'))
GRADE_COLOURS = {u'A+': u'#2E7D32', u'A': u'#558B2F', u'B': u'#EF6C00', u'C': u'#C62828'}
NEUTRAL = u'#BDBDBD'
OK_COLOUR, WARN_COLOUR = u'#2E7D32', u'#EF6C00'
INVALID_COLOUR = u'#D32F2F'


def selection_text(counts, marks=()):
    """'Selected: 2 beams (B10, B11) · 1 slab' from {kind: n} in KINDS order; marks shown up to four."""
    parts = []
    for kind, _tab, one, many in KINDS:
        n = counts.get(kind, 0)
        if n:
            parts.append(u'{} {}'.format(n, one if n == 1 else many))
    if not parts:
        return u'Nothing selected in the model: select the elements to reinforce, then Refresh selection.'
    shown = [m for m in marks if m][:4]
    tail = u' ({}{})'.format(u', '.join(shown), u', ...' if len([m for m in marks if m]) > 4 else u'') \
        if shown else u''
    return u'Selected: ' + u' · '.join(parts) + tail


def tab_for(counts):
    """The element tab the selection calls for: the kind with most elements, None with none."""
    best, most = None, 0
    for kind, tab, _one, _many in KINDS:
        n = counts.get(kind, 0)
        if n > most:
            best, most = tab, n
    return best


def first_line(text):
    """The first non-empty line of a run log, for the action bar."""
    for line in (text or u'').splitlines():
        line = line.strip()
        if line:
            return line
    return u''


def looks_failed(text):
    t = (text or u'').strip().lower()
    return t.startswith((u'no ', u'nothing', u'select')) or any(w in t for w in (u'error', u'failed', u'✗'))


def element_ids(line):
    """The Revit element ids a run log line names (5 to 9 digits, not a length with its unit)."""
    import re
    return [int(m) for m in re.findall(u'(?<![\\d.])(\\d{5,9})(?![\\d.]|\\s?mm)', line or u'')]


LIMIT_FIELDS = ('TxtDiaX', 'TxtSpacing', 'TxtTopDiaX', 'TxtTopSpacing', 'TxtWallVertDia', 'TxtWallVertSpacing',
                'TxtWallHorizDia', 'TxtWallHorizSpacing')


def _num(text, default):
    try:
        return float((text or u'').strip())
    except ValueError:
        return default


def number_ok(text, allow_auto=False):
    """True for a number (or 'Auto' where allowed): the fields' inline check."""
    t = (text or u'').strip()
    if allow_auto and t.lower() in (u'auto', u''):
        return True
    try:
        float(t)
        return True
    except ValueError:
        return False


def visible_for(tag, slab_filter):
    """A card tagged 'floors' shows on the Slabs tab, one tagged 'footings' on Bases & pile caps."""
    if tag == u'floors':
        return slab_filter != u'footings'
    if tag == u'footings':
        return slab_filter != u'floors'
    return True


SLAB_INTRO = {u'floors': u'Select floors and foundation slabs (rafts) in the model.',
              u'footings': u'Select pad and strip footings and pile caps in the model. The bars of the bottom mat '
                           u'and the dowels below are set here; the piles under a cap are found on their own.'}


class ShellMixin(object):

    def _init_shell(self):
        """Wire the shell after LoadComponent (no XAML event on a selector, see __init__)."""
        try:
            self.TxtDocInfo.Text = u'{} · IStructE SMDSC 4th ed. · EC2 (UK NA)'.format(self.doc.Title)
        except Exception:
            pass
        self._slab_grid = self.TabSlabs.Content
        self._slab_filter = u'floors'
        self._apply_category_visibility()
        self._defaults = {}
        for button, tab in DEFAULT_BUTTONS:
            self._defaults[tab] = self._field_values(getattr(self, tab))
            getattr(self, button).Click += self._reset_defaults
        self.BtnMinSlabs.Click += self._apply_min_slabs
        self.BtnMinWalls.Click += self._apply_min_walls
        for name in LIMIT_FIELDS:
            getattr(self, name).TextChanged += self._limits_changed
        self.BtnGenerate.Click += self._generate_active
        self.BtnNextStep.Click += self._next_step
        self.BtnRefreshSelection.Click += self._refresh_selection_click
        self.MainTabControl.SelectionChanged += self._shell_tab_changed
        for log in sorted(set(log for _tab, _handler, log in ELEMENT_TABS)):
            getattr(self, log).TextChanged += self._run_log_changed
            getattr(self, log).MouseDoubleClick += self._select_from_log
            getattr(self, log).ToolTip = u'Double-click a line naming an element to select it in the model.'
        self._wire_number_checks()
        self._refresh_selection()
        cfg = self.LoadConfig()
        tab = tab_for(self._selection_counts) or cfg.get('last_tab') or 'TabSlabs'
        self._select_tab(tab)
        self._update_generate_state()

    # ── navigation ───────────────────────────────────────────────────────

    def _select_tab(self, name):
        item = getattr(self, name, None)
        if item is not None:
            self._place_slab_form(name)
            self.MainTabControl.SelectedItem = item

    def _place_slab_form(self, name):
        """Slabs and Bases & pile caps share one form: it moves to the tab chosen, which filters what it acts on."""
        if name not in ('TabSlabs', 'TabBases'):
            return
        host, other = (self.TabSlabs, self.TabBases) if name == 'TabSlabs' else (self.TabBases, self.TabSlabs)
        if host.Content is not self._slab_grid:
            other.Content = None
            host.Content = self._slab_grid
        self._slab_filter = u'floors' if name == 'TabSlabs' else u'footings'
        self.TxtSlabsIntro.Text = SLAB_INTRO[self._slab_filter]
        self._apply_category_visibility()
        self._update_limits()

    def _slab_tab_hosts(self, footings, floors):
        """(footings, floors) the Slabs or Bases tab acts on: foundation slabs go with the floors."""
        slabs = [f for f in footings if isinstance(f, DB.Floor)]
        bases = [f for f in footings if not isinstance(f, DB.Floor)]
        if getattr(self, '_slab_filter', None) == u'footings':
            return bases, []
        if getattr(self, '_slab_filter', None) == u'floors':
            return slabs, floors
        return footings, floors

    def _active_tab(self):
        item = self.MainTabControl.SelectedItem
        try:
            return item.Name
        except Exception:
            return u''

    def _shell_tab_changed(self, sender, args):
        if not getattr(self, '_is_loaded', False) or args.Source is not self.MainTabControl:
            return
        self._place_slab_form(self._active_tab())
        self._update_generate_state()
        try:
            cfg = self.LoadConfig()
            cfg['last_tab'] = self._active_tab()
            self.SaveConfig(cfg)
        except Exception:
            pass

    def _update_generate_state(self):
        element = [t for t, _h, _l in ELEMENT_TABS]
        on = self._active_tab() in element
        self.BtnGenerate.IsEnabled = on
        self.BtnGenerate.ToolTip = (u'Generate the reinforcement of the selected elements with this tab\'s values.'
                                    if on else u'Choose an element (Slabs & bases ... Stairs) to generate.')

    # ── GENERATE and the next step ──────────────────────────────────────

    def _generate_active(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        name = self._active_tab()
        if self._frozen_selection():
            return
        for tab, handler, _log in ELEMENT_TABS:
            if tab == name:
                self._last_run_tab = tab
                getattr(self, handler)(sender, args)
                return

    def _next_step(self, sender, args):
        self._select_tab('TabDrawings')

    def _run_log_changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        text = sender.Text or u''
        line = first_line(text)
        if not line or line == u'No run yet.':
            return
        self.TxtActionStatus.Text = line
        failed = looks_failed(line)
        self._set_fill(self.DotStatus, WARN_COLOUR if failed else OK_COLOUR)
        if not failed:
            from System.Windows import Visibility
            self.BtnNextStep.Visibility = Visibility.Visible
            self._show_grade()

    def _select_from_log(self, sender, args):
        """A run log's notes are links: the elements its double-clicked line names get selected in the model."""
        try:
            index = sender.GetLineIndexFromCharacterIndex(sender.CaretIndex)
            ids = element_ids(sender.GetLineText(index))
            if not ids:
                return
            from System.Collections.Generic import List
            from nosa_utils.revit_helpers import element_id_from_int
            found = [element_id_from_int(i) for i in ids if self.doc.GetElement(element_id_from_int(i)) is not None]
            if found:
                self.uidoc.Selection.SetElementIds(List[DB.ElementId](found))
                self.TxtActionStatus.Text = u'{} element(s) selected in the model from the run log.'.format(len(found))
        except Exception:
            pass

    # ── QA badge ────────────────────────────────────────────────────────

    def _show_grade(self):
        """The buildability grade of the selected members (rebar_qa, read-only); hidden when it cannot run."""
        from System.Windows import Visibility
        try:
            from nosa_utils import rebar_qa
            ids = list(self.uidoc.Selection.GetElementIds())
            if not ids:
                return
            score, grade, errors, warns = rebar_qa.buildability(rebar_qa.audit(self.doc, ids))
        except Exception:
            self.BadgeQA.Visibility = Visibility.Collapsed
            return
        self.TxtQAGrade.Text = u'QA {}  {:.0f}'.format(grade, score)
        self.BadgeQA.ToolTip = (u'Buildability {} ({:.0f}/100): {} error(s), {} warning(s) - Check & manage, '
                                u'Rebar QA for the list. A+ ready to issue, A minor points, B to review, C not '
                                u'buildable as drawn.').format(grade, score, errors, warns)
        self._set_fill(self.BadgeQA, GRADE_COLOURS.get(grade, NEUTRAL), background=True)
        self.BadgeQA.Visibility = Visibility.Visible

    # ── selection ───────────────────────────────────────────────────────

    def _refresh_selection_click(self, sender, args):
        self._refresh_selection()
        tab = tab_for(self._selection_counts)
        if tab and self._active_tab() not in (t for t, _h, _l in ELEMENT_TABS):
            self._select_tab(tab)
        try:
            self._update_preview()
            self._update_column_preview()
            self._update_beam_preview()
            self._update_wall_preview()
            self._update_stair_preview()
        except Exception:
            pass

    def _refresh_selection(self):
        counts, marks = {}, []
        try:
            footings, floors = self._selected_hosts()
            groups = (('slab', floors + [f for f in footings if isinstance(f, DB.Floor)]),
                      ('base', [f for f in footings if not isinstance(f, DB.Floor)]),
                      ('column', self._selected_columns()),
                      ('beam', self._selected_beams()), ('wall', self._selected_walls()),
                      ('stair', self._selected_stairs()))
        except Exception:
            groups = ()
        for kind, elements in groups:
            if elements:
                counts[kind] = len(elements)
                for e in elements:
                    try:
                        p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                        marks.append((p.AsString() or u'').strip() if p is not None else u'')
                    except Exception:
                        marks.append(u'')
        self._selection_counts = counts
        self.TxtSelection.Text = selection_text(counts, marks)
        self._set_fill(self.DotSelection, OK_COLOUR if counts else NEUTRAL)
        if hasattr(self, '_slab_filter'):
            self._update_limits()

    def _apply_category_visibility(self):
        """Slab-only cards on Slabs, base-only cards on Bases & pile caps (principle 3)."""
        from System.Windows import Visibility
        for border in self._tagged_cards():
            border.Visibility = Visibility.Visible if visible_for(border.Tag, self._slab_filter) else Visibility.Collapsed

    def _tagged_cards(self):
        from System.Windows.Controls import Border
        return [c for c in self._descendants(self._slab_grid) if isinstance(c, Border) and c.Tag in (u'floors', u'footings')]

    # ── detailing limits (T10.7): EC2 minimum and maximum pitch ─────────

    def _limits_changed(self, sender, args):
        if getattr(self, '_is_loaded', False):
            self._update_limits()

    def _mesh_hosts(self):
        """[(host, thickness mm)] of the Slabs / Bases tab's selection."""
        try:
            footings, floors = self._slab_tab_hosts(*self._selected_hosts())
        except Exception:
            return []
        out = []
        for h in footings + floors:
            bb = h.get_BoundingBox(None)
            if bb is not None:
                out.append((h, (bb.Max.Z - bb.Min.Z) * 304.8))
        return out

    def _slab_limits(self):
        """(As,min, main pitch max, secondary pitch max, thickest h) over the selection, or None."""
        from nosa_utils import min_steel
        hosts = self._mesh_hosts()
        if not hosts:
            return None
        rows = []
        for host, h in hosts:
            try:
                cover = self._preview_cover_mm(host, u'Bottom', u'slab')
                fck = re_engine.host_fck_mpa(self.doc, host) or float(self.ra_project.get('default_fck_mpa') or 32.0)
            except Exception:
                cover, fck = 30.0, 32.0
            rows.append(min_steel.slab_limits(h, cover, _num(self.TxtDiaX.Text, 12.0), fck) + (h,))
        return (max(r[0] for r in rows), min(r[1] for r in rows), min(r[2] for r in rows), max(r[3] for r in rows))

    def _wall_limits(self):
        from nosa_utils import min_steel
        walls = self._selected_walls()
        if not walls:
            return None
        rows = [min_steel.wall_limits(w.Width * 304.8) + (w.Width * 304.8,) for w in walls]
        return (max(r[0] for r in rows), max(r[1] for r in rows), min(r[2] for r in rows), min(r[3] for r in rows),
                max(r[4] for r in rows))

    def _update_limits(self):
        from nosa_utils import min_steel
        lim = self._slab_limits()
        if lim is None:
            self.TxtLimitsSlabs.Text = u'Select an element to see its minimum steel and maximum pitch.'
            self._set_text_colour(self.TxtLimitsSlabs, None)
        else:
            as_min, main, sec, h = lim
            issues = min_steel.check(_num(self.TxtDiaX.Text, 0), _num(self.TxtSpacing.Text, 0), as_min, main)
            if self.ChkIncludeTopMat.IsChecked == True:
                issues += [u'top: ' + i for i in min_steel.check(_num(self.TxtTopDiaX.Text, 0),
                                                                   _num(self.TxtTopSpacing.Text, 0), as_min, main)]
            self.TxtLimitsSlabs.Text = (u'h {:.0f}: As,min {:.0f} mm\u00b2/m each way; pitch at most {:.0f} main, '
                                        u'{:.0f} secondary. {}').format(
                h, as_min, main, sec, u'Below the limits: ' + u'; '.join(issues) if issues else u'The mats meet them.')
            self._set_text_colour(self.TxtLimitsSlabs, WARN_COLOUR if issues else None)
        lim = self._wall_limits()
        if lim is None:
            self.TxtLimitsWalls.Text = u'Select a wall to see its minimum steel and maximum pitch.'
            self._set_text_colour(self.TxtLimitsWalls, None)
        else:
            v, hz, pv, ph, h = lim
            issues = [u'vertical: ' + i for i in min_steel.check(_num(self.TxtWallVertDia.Text, 0),
                                                                 _num(self.TxtWallVertSpacing.Text, 0), v, pv)]
            issues += [u'horizontal: ' + i for i in min_steel.check(_num(self.TxtWallHorizDia.Text, 0),
                                                                     _num(self.TxtWallHorizSpacing.Text, 0), hz, ph)]
            self.TxtLimitsWalls.Text = (u'{:.0f} thick: each face at least {:.0f} mm\u00b2/m vertical, {:.0f} '
                                        u'horizontal; pitch at most {:.0f} / {:.0f}. {}').format(
                h, v, hz, pv, ph, u'Below the limits: ' + u'; '.join(issues) if issues else u'The meshes meet them.')
            self._set_text_colour(self.TxtLimitsWalls, WARN_COLOUR if issues else None)

    def _apply_min_slabs(self, sender, args):
        from nosa_utils import min_steel
        lim = self._slab_limits()
        if lim is None:
            self.TxtActionStatus.Text = u'Select the slabs or bases first: the minimum depends on their thickness.'
            return
        dia, pitch = min_steel.lightest(lim[0], lim[1])
        self.TxtDiaX.Text = self.TxtDiaY.Text = u'{:d}'.format(dia)
        self.TxtSpacing.Text = u'{:.0f}'.format(pitch)
        if self.ChkIncludeTopMat.IsChecked == True:
            self.TxtTopDiaX.Text = self.TxtTopDiaY.Text = u'{:d}'.format(dia)
            self.TxtTopSpacing.Text = u'{:.0f}'.format(pitch)
        self.TxtActionStatus.Text = u'EC2 minimum filled: H{} at {:.0f} - a minimum, not a design.'.format(dia, pitch)

    def _apply_min_walls(self, sender, args):
        from nosa_utils import min_steel
        lim = self._wall_limits()
        if lim is None:
            self.TxtActionStatus.Text = u'Select the walls first: the minimum depends on their thickness.'
            return
        dv, pv = min_steel.lightest(lim[0], lim[2])
        dh, ph = min_steel.lightest(lim[1], lim[3])
        self.TxtWallVertDia.Text, self.TxtWallVertSpacing.Text = u'{:d}'.format(dv), u'{:.0f}'.format(pv)
        self.TxtWallHorizDia.Text, self.TxtWallHorizSpacing.Text = u'{:d}'.format(dh), u'{:.0f}'.format(ph)
        self.TxtActionStatus.Text = (u'EC2 minimum filled: vertical H{} at {:.0f}, horizontal H{} at {:.0f} each '
                                     u'face - a minimum, not a design.').format(dv, pv, dh, ph)

    @staticmethod
    def _set_text_colour(block, colour):
        from System.Windows.Media import BrushConverter
        if colour is None:
            block.SetResourceReference(block.ForegroundProperty, 'TextColor')
        else:
            block.Foreground = BrushConverter().ConvertFromString(colour)

    # ── fields: inline check and defaults ──────────────────────────────

    @staticmethod
    def _descendants(node):
        from System.Windows import LogicalTreeHelper, DependencyObject
        out, stack = [], [node]
        while stack:
            n = stack.pop()
            for child in LogicalTreeHelper.GetChildren(n):
                if isinstance(child, DependencyObject):
                    out.append(child)
                    stack.append(child)
        return out

    def _field_values(self, tab):
        from System.Windows.Controls import TextBox, CheckBox
        out = {}
        for c in self._descendants(tab):
            if isinstance(c, TextBox) and c.Name and not c.IsReadOnly:
                out[c.Name] = (u'text', c.Text)
            elif isinstance(c, CheckBox) and c.Name:
                out[c.Name] = (u'check', c.IsChecked == True)
        return out

    def _reset_defaults(self, sender, args):
        tab = dict(DEFAULT_BUTTONS).get(sender.Name)
        for name, (kind, value) in self._defaults.get(tab, {}).items():
            control = getattr(self, name, None)
            if control is None:
                continue
            if kind == u'text':
                control.Text = value
            else:
                control.IsChecked = value
        # the panels a check box enables follow it
        for check, panel in (('ChkIncludeTopMat', 'PanelTopMat'), ('ChkIncludeSideRebar', 'PanelSideRebar'),
                             ('ChkIncludeDowels', 'PanelDowels'), ('ChkIncludePerimeterUBars', 'PanelPerimeterUBars'),
                             ('ChkOpeningDiagonals', 'PanelOpeningDiagonals'), ('ChkColDensify', 'PanelColDensify'),
                             ('ChkColCrossties', 'PanelColCrossties'),
                             ('ChkColFoundationStarters', 'PanelColFoundationStarters')):
            c, p = getattr(self, check, None), getattr(self, panel, None)
            if c is not None and p is not None:
                p.IsEnabled = c.IsChecked == True

    def _wire_number_checks(self):
        from System.Windows.Controls import TextBox
        for tab, _h, _l in ELEMENT_TABS:
            for c in self._descendants(getattr(self, tab)):
                if isinstance(c, TextBox) and c.Name and not c.IsReadOnly and c.HorizontalContentAlignment.ToString() == 'Right':
                    c.TextChanged += self._check_number

    def _check_number(self, sender, args):
        from System.Windows.Media import BrushConverter
        ok = number_ok(sender.Text, allow_auto=u'Splice' in (sender.Name or u''))
        if ok:
            sender.ClearValue(sender.BorderBrushProperty)
            sender.ToolTip = None
        else:
            sender.BorderBrush = BrushConverter().ConvertFromString(INVALID_COLOUR)
            sender.ToolTip = u'A number, please' + (u' (or Auto)' if u'Splice' in (sender.Name or u'') else u'') + u'.'

    @staticmethod
    def _set_fill(element, colour, background=False):
        from System.Windows.Media import BrushConverter
        brush = BrushConverter().ConvertFromString(colour)
        if background:
            element.Background = brush
        else:
            element.Fill = brush


_OWN = set(globals())
