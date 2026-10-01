# -*- coding: utf-8 -*-
import io, csv, os, sys, imp
import System.Windows
import System.Windows.Media
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                     '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
from nosa_utils.telemetry import log_swallowed
from nosa_utils.logging import Logger
from nosa_utils.revit_helpers import get_id_value, element_id_from_int
_LOG = u'StructuralQA/ui'

_here = os.path.dirname(os.path.abspath(__file__))
_cr_logic = imp.load_source('sqa_cr_logic', os.path.join(_here, 'logic_clash_report.py'))
_dc_logic = imp.load_source('sqa_dc_logic', os.path.join(_here, 'logic_drawing_checker.py'))
_fa_logic = imp.load_source('sqa_fa_logic', os.path.join(_here, 'logic_family_audit.py'))
_iq_logic = imp.load_source('sqa_iq_logic', os.path.join(_here, 'logic_ifc_export_qa.py'))
_si_logic = imp.load_source('sqa_si_logic', os.path.join(_here, 'logic_schedule_impact.py'))
_rc_logic = imp.load_source('sqa_rc_logic', os.path.join(_here, 'logic_rebar_coverage.py'))
_qq_logic = imp.load_source('sqa_qq_logic', os.path.join(_here, 'logic_quantification_qa.py'))

CR_ClashLogic = _cr_logic.ClashLogic

logger = Logger()


# ══════════════════════════════════════════════════════════════════
# Row / item classes
# ══════════════════════════════════════════════════════════════════

class CR_CategoryItem(object):
    def __init__(self, name, category, count):
        self.Name      = "{} ({})".format(name, count)
        self.Category  = category
        self.RawName   = name
        self.Count     = count
        self.IsChecked = False


class CR_ClashResultItem(object):
    def __init__(self, index, clash_tuple, volume=0.0):
        info1, info2 = clash_tuple
        self.Index    = index
        self.Name1    = info1['name']
        self.Id1      = info1['id']
        self.Cat1     = info1['category']
        self.Name2    = info2['name']
        self.Id2      = info2['id']
        self.Cat2     = info2['category']
        self.Volume   = round(volume * 0.0283168, 6) if volume else 0.0
        if self.Volume > 0.01:
            self.Severity = "High"
        elif self.Volume > 0.001:
            self.Severity = "Medium"
        else:
            self.Severity = "Low"
        self.VolumeStr = "{:.4f} m³".format(self.Volume) if self.Volume > 0 else "—"


_CR_STRUCTURAL_CATS = None


def _cr_structural_cats():
    global _CR_STRUCTURAL_CATS
    if _CR_STRUCTURAL_CATS is None:
        _CR_STRUCTURAL_CATS = [
            ("Structural Columns",     DB.BuiltInCategory.OST_StructuralColumns),
            ("Structural Framing",     DB.BuiltInCategory.OST_StructuralFraming),
            ("Structural Foundations", DB.BuiltInCategory.OST_StructuralFoundation),
            ("Floors",                 DB.BuiltInCategory.OST_Floors),
            ("Walls",                  DB.BuiltInCategory.OST_Walls),
            ("Columns",                DB.BuiltInCategory.OST_Columns),
            ("Pipes",                  DB.BuiltInCategory.OST_PipeCurves),
            ("Ducts",                  DB.BuiltInCategory.OST_DuctCurves),
            ("Cable Trays",            DB.BuiltInCategory.OST_CableTray),
            ("Conduits",               DB.BuiltInCategory.OST_Conduit),
        ]
    return _CR_STRUCTURAL_CATS


_DC_STATUS_EMOJI = {'green': u'✅', 'amber': u'⚠', 'red': u'❌'}
_DC_STATUS_COLOR = {'green': '#22c55e', 'amber': '#f59e0b', 'red': '#ef4444'}


class FA_FamilyRow(object):
    def __init__(self, data):
        self.Id            = data['id']
        self.Name          = data['name']
        self.Category      = data['category']
        self.TypeCount     = data['type_count']
        self.InstanceCount = data['instance_count']
        self.SizeMB        = '{:.3f}'.format(data['size_mb']) if data['size_mb'] else '—'
        self.ParamFill     = '{:.0%}'.format(data['completeness'])
        self.Editable      = 'Yes' if data['is_editable'] else 'No'
        self.IsChecked     = False
        self.IsUnused      = data['instance_count'] == 0
        self._family       = data['family']
        self._raw          = data


_FA_SEARCH_PH = "Search families..."
_FA_ALL_CATS  = "All Categories"

_IQ_STATUS_COLOUR = {'green': '#22c55e', 'amber': '#f59e0b', 'red': '#ef4444'}


class SI_ImpactRow(object):
    def __init__(self, r):
        self.ScheduleName = r.get('schedule_name', u'')
        self.FieldCount   = u'{}'.format(r.get('field_count', 0))
        self.SheetCount   = u'{}'.format(r.get('sheet_count', 0))
        self.Sheets       = u', '.join(
            u'{} — {}'.format(s[0], s[1]) for s in r.get('sheets', []))
        self.ScheduleId   = r.get('schedule_id', 0)


class SI_CatItem(object):
    def __init__(self, name, cat):
        self.Name = name
        self._cat = cat

    @property
    def CategoryId(self):
        try:
            return get_id_value(self._cat.Id)
        except Exception:
            return -1


class RC_MissingRow(object):
    def __init__(self, d):
        self.Category = d['category']
        self.Level    = d['level']
        self.Name     = d['name']
        self.Id       = d['id']


class RC_SummaryRow(object):
    def __init__(self, d):
        self.Category     = d['category']
        self.WithRebar    = d['with_rebar']
        self.WithoutRebar = d['without_rebar']
        self.Coverage     = "{}%".format(d['coverage'])


class QQ_QuantRow(object):
    """Row for the Concrete tab."""
    def __init__(self, d):
        self.Category = d.get('category', '')
        self.Material = d.get('material', '')
        self.Level    = d.get('level', '')
        self.VolStr   = '{:.3f}'.format(d.get('volume_m3', 0))
        self.AreaStr  = '{:.2f}'.format(d.get('area_m2', 0))
        self.Count    = d.get('count', 0)


class QQ_SteelRow(object):
    """Row for the Steel tab."""
    def __init__(self, d):
        self.Category    = d.get('category', '')
        self.Material    = d.get('material', '')
        self.Level       = d.get('level', '')
        self.WeightKg    = '{:.1f}'.format(d.get('weight_kg', 0))
        self.WeightTonne = '{:.3f}'.format(d.get('weight_t', 0))
        self.Count       = d.get('count', 0)


class QQ_RebarRow(object):
    """Row for the Rebar tab."""
    def __init__(self, d):
        self.Level     = d.get('level', '')
        self.DiamStr   = '{:.0f}'.format(d.get('diam_mm', 0))
        self.Count     = d.get('count', 0)
        self.LengthStr = '{:.2f}'.format(d.get('total_length_m', 0))
        self.WeightStr = '{:.1f}'.format(d.get('weight_kg', 0))


class QQ_QARow(object):
    def __init__(self, d):
        self.Severity = d.get('severity', '')
        self.Category = d.get('category', '')
        self.Level    = d.get('level', '')
        self.Name     = d.get('name', '')
        self.Problem  = d.get('problem', '')
        self.Id       = d.get('id')


class StructuralQAWindow(NOSAWindow):

    def __init__(self, doc):
        # Handlers wired in code check this so no early SelectionChanged
        # reaches them before __init__ has finished (see RebarAutomate).
        self._is_loaded = False

        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'structural_qa_hub')
        self.doc = doc

        cfg = self.LoadConfig()
        self.ApplyTheme(cfg.get('dark_mode', False))
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', False)

        self._cr_init()
        self._dc_init()
        self._fa_init()
        self._iq_init()
        self._si_init()
        self._rc_init()
        self._qq_init()

        self._is_loaded = True

    # ══════════════════════════════════════════════════════════════════
    # TAB 1: CLASH REPORT
    # ══════════════════════════════════════════════════════════════════

    def _cr_init(self):
        self._cr_engine = CR_ClashLogic(self.doc)
        self._cr_categories = ObservableCollection[CR_CategoryItem]()
        self._cr_results    = ObservableCollection[CR_ClashResultItem]()
        self.CR_ListCategories.ItemsSource = self._cr_categories
        self.CR_GridResults.ItemsSource    = self._cr_results
        self._cr_load_categories()

    def _cr_load_categories(self):
        for name, cat in _cr_structural_cats():
            elements = self._cr_engine.collect_elements_by_category(cat)
            if elements:
                self._cr_categories.Add(CR_CategoryItem(name, cat, len(elements)))

    def CR_Run_Click(self, sender, args):
        selected = list(self.CR_ListCategories.SelectedItems) if self.CR_ListCategories.SelectedItems else []
        if len(selected) < 2:
            forms.alert("Select at least 2 categories to check.")
            return

        pair_product = 0
        for i in range(len(selected)):
            for j in range(i + 1, len(selected)):
                pair_product += selected[i].Count * selected[j].Count
        if pair_product > 2000000:
            if not forms.alert(
                    u'This check will evaluate roughly {:,} element pairs and '
                    u'may take several minutes.\n\nContinue?'.format(pair_product),
                    title=u'Clash Report — Large model', yes=True, no=True):
                return

        self.SetLoading(True, "Collecting elements...")
        self._cr_results.Clear()
        self.CR_TxtSummary.Text = ""
        self.CR_BtnExportCSV.IsEnabled  = False
        self.CR_BtnExportHTML.IsEnabled = False
        self.CR_BtnExportBCF.IsEnabled  = False

        try:
            self._cr_run_clash_check(selected)
        except Exception as e:
            forms.alert("Error during clash check: {}".format(e))
        finally:
            self.SetLoading(False)

        self.CR_BtnExportCSV.IsEnabled  = len(self._cr_results) > 0
        self.CR_BtnExportHTML.IsEnabled = len(self._cr_results) > 0
        self.CR_BtnExportBCF.IsEnabled  = len(self._cr_results) > 0

    def _cr_run_clash_check(self, selected_cats):
        self._cr_engine.clear_solid_cache()
        all_elements = []
        for cat_item in selected_cats:
            self.SetLoading(True, "Collecting {}...".format(cat_item.RawName))
            elements = self._cr_engine.collect_elements_by_category(cat_item.Category)
            for el in elements:
                bbox = self._cr_engine.get_element_bounding_box(el)
                if bbox:
                    all_elements.append((el, bbox, cat_item.RawName))

        total = len(all_elements)
        self.SetLoading(True, "Checking {} elements...".format(total))

        clashes     = []
        clash_pairs = set()
        order = sorted(range(total), key=lambda i: all_elements[i][1].Min.X)

        for ii in range(total):
            i = order[ii]
            elem1, bbox1, cat1 = all_elements[i]
            if ii % 50 == 0:
                self.SetLoading(True, "Sweep {}/{}...".format(ii, total))

            for jj in range(ii + 1, total):
                j = order[jj]
                elem2, bbox2, cat2 = all_elements[j]
                if bbox2.Min.X > bbox1.Max.X:
                    break
                if elem1.Id == elem2.Id:
                    continue
                pair_key = tuple(sorted([
                    self._cr_engine.get_id_value(elem1.Id),
                    self._cr_engine.get_id_value(elem2.Id)
                ]))
                if pair_key in clash_pairs:
                    continue
                if not self._cr_engine.bounding_boxes_intersect(bbox1, bbox2):
                    continue
                solid1 = self._cr_engine.get_element_solid_cached(elem1)
                solid2 = self._cr_engine.get_element_solid_cached(elem2)
                if solid1 and solid2:
                    vol = self._cr_engine.intersect_volume(solid1, solid2)
                    if vol > 0:
                        clash_pairs.add(pair_key)
                        info1 = self._cr_engine.get_element_info(elem1)
                        info2 = self._cr_engine.get_element_info(elem2)
                        clashes.append((info1, info2, vol))

        for idx, clash in enumerate(clashes):
            vol = clash[2] if len(clash) > 2 else 0.0
            self._cr_results.Add(CR_ClashResultItem(idx + 1, clash, vol))

        high   = sum(1 for r in self._cr_results if r.Severity == 'High')
        medium = sum(1 for r in self._cr_results if r.Severity == 'Medium')
        low    = sum(1 for r in self._cr_results if r.Severity == 'Low')
        self.CR_TxtSummary.Text = "{} clashes — {} High  {} Medium  {} Low".format(
            len(clashes), high, medium, low)

    def CR_Grid_SelectionChanged(self, sender, args):
        has = self.CR_GridResults.SelectedItem is not None
        self.CR_BtnIsolate.IsEnabled    = has
        self.CR_BtnSelectBoth.IsEnabled = has

    def CR_SelectBoth_Click(self, sender, args):
        item = self.CR_GridResults.SelectedItem
        if not item:
            return
        try:
            ids = List[DB.ElementId]([element_id_from_int(item.Id1),
                                      element_id_from_int(item.Id2)])
            revit.uidoc.Selection.SetElementIds(ids)
            try:
                revit.uidoc.ShowElements(ids)
            except Exception:
                log_swallowed(_LOG, u'CR_SelectBoth_Click')
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def CR_Isolate_Click(self, sender, args):
        item = self.CR_GridResults.SelectedItem
        if not item:
            return
        try:
            ids = List[DB.ElementId]([element_id_from_int(item.Id1),
                                      element_id_from_int(item.Id2)])
            with revit.Transaction(u"NOSA — Isolate Clash"):
                revit.active_view.IsolateElementsTemporary(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Error isolating: {}".format(e))

    def CR_ExportCSV_Click(self, sender, args):
        if not self._cr_results:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['#', 'Severity', 'Volume (m³)',
                            'Element 1', 'Category 1', 'ID 1',
                            'Element 2', 'Category 2', 'ID 2'])
                for r in self._cr_results:
                    w.writerow([r.Index, r.Severity, r.VolumeStr,
                                r.Name1, r.Cat1, r.Id1,
                                r.Name2, r.Cat2, r.Id2])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    def CR_ExportHTML_Click(self, sender, args):
        if not self._cr_results:
            return
        path = forms.save_file(file_ext='html')
        if not path:
            return

        from collections import Counter
        pair_counts = Counter()
        for item in self._cr_results:
            key = tuple(sorted([item.Cat1, item.Cat2]))
            pair_counts[key] += 1

        sev_color = {'High': '#FFDDDD', 'Medium': '#FFE8CC', 'Low': '#F5F5F5'}
        rows_html = ''
        for item in self._cr_results:
            bg = sev_color.get(item.Severity, '#FFFFFF')
            rows_html += (
                "<tr style='background:{bg}'>"
                "<td>{idx}</td><td>{sev}</td><td>{vol}</td>"
                "<td>{n1} <small style='color:#888'>[{c1}] ID:{id1}</small></td>"
                "<td>{n2} <small style='color:#888'>[{c2}] ID:{id2}</small></td>"
                "</tr>"
            ).format(bg=bg, idx=item.Index, sev=item.Severity, vol=item.VolumeStr,
                     n1=item.Name1, c1=item.Cat1, id1=item.Id1,
                     n2=item.Name2, c2=item.Cat2, id2=item.Id2)

        summary_rows = ''
        for (c1, c2), cnt in sorted(pair_counts.items(), key=lambda x: -x[1]):
            summary_rows += "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(c1, c2, cnt)

        html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>body{{font-family:'Century Gothic',sans-serif;padding:20px;color:#333}}"
            "h1{{color:#FF5F00}}table{{border-collapse:collapse;width:100%;margin-top:10px}}"
            "th{{background:#FF5F00;color:white;padding:8px 10px;text-align:left}}"
            "td{{padding:6px 10px;border-bottom:1px solid #eee}}</style></head><body>"
            "<h1>NOSA — Clash Report</h1><p>{total} clashes detected</p>"
            "<h2>Category Summary</h2><table><tr><th>Category A</th><th>Category B</th><th>Clashes</th></tr>"
            "{summary}</table>"
            "<h2>All Clashes</h2><table><tr><th>#</th><th>Severity</th><th>Volume</th>"
            "<th>Element 1</th><th>Element 2</th></tr>{rows}</table>"
            "</body></html>"
        ).format(total=len(list(self._cr_results)), summary=summary_rows, rows=rows_html)

        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(html)
            import subprocess
            subprocess.Popen(['start', path], shell=True)
        except Exception as e:
            forms.alert("Export error: {}".format(e))

    def CR_ExportBCF_Click(self, sender, args):
        if not self._cr_results:
            return
        path = forms.save_file(file_ext='bcf')
        if not path:
            return
        if not path.lower().endswith('.bcf'):
            path += '.bcf'
        try:
            self._cr_write_bcf(path)
            forms.alert("BCF 2.1 exported:\n{}".format(path))
        except Exception as e:
            forms.alert("BCF export failed: {}".format(e))

    def _cr_write_bcf(self, bcf_path):
        import zipfile, uuid, datetime
        now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        with zipfile.ZipFile(bcf_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('bcf.version', (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Version VersionId="2.1" xsi:noNamespaceSchemaLocation="version.xsd"'
                ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                '<DetailedVersion>2.1</DetailedVersion></Version>'
            ))

            for item in self._cr_results:
                topic_id = str(uuid.uuid4())
                folder = topic_id + '/'

                priority = {'High': 'Major', 'Medium': 'Normal', 'Low': 'Minor'}.get(
                    item.Severity, 'Normal')
                markup = (
                    u'<?xml version="1.0" encoding="UTF-8"?>\n'
                    u'<Markup xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
                    u'  <Topic Guid="{guid}" TopicType="Clash" TopicStatus="Open">\n'
                    u'    <Title>Clash #{idx}: {n1} vs {n2}</Title>\n'
                    u'    <Priority>{prio}</Priority>\n'
                    u'    <CreationDate>{date}</CreationDate>\n'
                    u'    <CreationAuthor>NOSA ClashReport</CreationAuthor>\n'
                    u'    <Description>'
                    u'Clash between {n1} (ID {id1}, {c1}) and {n2} (ID {id2}, {c2}). '
                    u'Overlap volume: {vol}</Description>\n'
                    u'  </Topic>\n'
                    u'  <Header>\n'
                    u'    <File IfcProject="NOSA" IfcSpatialStructureElement="">\n'
                    u'      <Filename>model.rvt</Filename>\n'
                    u'    </File>\n'
                    u'  </Header>\n'
                    u'</Markup>\n'
                ).format(
                    guid=topic_id, idx=item.Index,
                    n1=item.Name1, n2=item.Name2,
                    id1=item.Id1, id2=item.Id2,
                    c1=item.Cat1, c2=item.Cat2,
                    vol=item.VolumeStr, date=now, prio=priority
                )
                zf.writestr(folder + 'markup.bcf', markup.encode('utf-8'))

                viewpoint = (
                    u'<?xml version="1.0" encoding="UTF-8"?>\n'
                    u'<VisualizationInfo Guid="{guid}">\n'
                    u'  <Components>\n'
                    u'    <Component IfcGuid="" AuthoringToolId="{id1}"/>\n'
                    u'    <Component IfcGuid="" AuthoringToolId="{id2}"/>\n'
                    u'  </Components>\n'
                    u'</VisualizationInfo>\n'
                ).format(guid=str(uuid.uuid4()), id1=item.Id1, id2=item.Id2)
                zf.writestr(folder + 'viewpoint.bcfv', viewpoint.encode('utf-8'))

    # ══════════════════════════════════════════════════════════════════
    # TAB 2: DRAWING CHECKER
    # ══════════════════════════════════════════════════════════════════

    def _dc_init(self):
        self._dc_results = []

    def _dc_run_checks(self):
        self.SetLoading(True, u'Running checks…')
        try:
            self._dc_results = _dc_logic.run_all_checks(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error running checks:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._dc_render_results()

    def _dc_render_results(self):
        import System.Windows.Controls as WC
        import System.Windows.Media as Media
        import System.Windows

        panel = self.DC_ResultsPanel
        panel.Children.Clear()

        overall = 'green'
        for r in self._dc_results:
            if r.status == 'red':
                overall = 'red'
                break
            if r.status == 'amber' and overall == 'green':
                overall = 'amber'

        banner = WC.Border()
        banner.CornerRadius = System.Windows.CornerRadius(6)
        banner.Padding = System.Windows.Thickness(12, 8, 12, 8)
        banner.Margin  = System.Windows.Thickness(0, 0, 0, 12)
        banner.Background = Media.SolidColorBrush(
            Media.ColorConverter.ConvertFromString(_DC_STATUS_COLOR[overall]))
        lbl = WC.TextBlock()
        lbl.Text = u'{} Overall: {}'.format(
            _DC_STATUS_EMOJI[overall],
            {'green': 'READY TO ISSUE', 'amber': 'REVIEW RECOMMENDED', 'red': 'ISSUES FOUND'}[overall]
        )
        lbl.FontWeight = System.Windows.FontWeights.Bold
        lbl.FontSize = 14
        lbl.Foreground = Media.Brushes.White
        banner.Child = lbl
        panel.Children.Add(banner)

        for r in self._dc_results:
            card = WC.Border()
            card.BorderThickness = System.Windows.Thickness(0, 0, 0, 0)
            card.CornerRadius = System.Windows.CornerRadius(6)
            card.Padding = System.Windows.Thickness(12, 10, 12, 10)
            card.Margin  = System.Windows.Thickness(0, 0, 0, 8)
            card.Background = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(
                    {'green': '#f0fdf4', 'amber': '#fffbeb', 'red': '#fef2f2'}[r.status]))
            left_border = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(_DC_STATUS_COLOR[r.status]))

            sp = WC.StackPanel()

            hdr = WC.StackPanel()
            hdr.Orientation = System.Windows.Controls.Orientation.Horizontal
            ico = WC.TextBlock()
            ico.Text = _DC_STATUS_EMOJI[r.status]
            ico.FontSize = 14
            ico.Margin = System.Windows.Thickness(0, 0, 8, 0)
            hdr.Children.Add(ico)
            title_tb = WC.TextBlock()
            title_tb.Text = r.check_name
            title_tb.FontWeight = System.Windows.FontWeights.SemiBold
            title_tb.FontSize = 12
            hdr.Children.Add(title_tb)
            count_tb = WC.TextBlock()
            count_tb.Text = u'  ({} issue{})'.format(r.count, '' if r.count == 1 else 's')
            count_tb.FontSize = 11
            count_tb.Opacity = 0.6
            hdr.Children.Add(count_tb)
            sp.Children.Add(hdr)

            if r.detail:
                for d in r.detail[:8]:
                    dtb = WC.TextBlock()
                    dtb.Text = u'  · ' + d
                    dtb.FontSize = 10
                    dtb.Opacity = 0.7
                    dtb.Margin = System.Windows.Thickness(0, 2, 0, 0)
                    sp.Children.Add(dtb)
                if len(r.detail) > 8:
                    more = WC.TextBlock()
                    more.Text = u'  … and {} more'.format(len(r.detail) - 8)
                    more.FontSize = 10
                    more.Opacity = 0.5
                    sp.Children.Add(more)

            card.Child = sp
            panel.Children.Add(card)

    def DC_Refresh_Click(self, sender, args):
        self._dc_run_checks()

    # ══════════════════════════════════════════════════════════════════
    # TAB 3: FAMILY AUDIT
    # ══════════════════════════════════════════════════════════════════

    def _fa_init(self):
        self._fa_all_rows = []
        self._fa_rows     = ObservableCollection[FA_FamilyRow]()
        self.FA_GridFamilies.ItemsSource = self._fa_rows
        self._fa_search_on = False
        self.FA_CboCategory.ItemsSource   = [_FA_ALL_CATS]
        self.FA_CboCategory.SelectedIndex = 0
        self.FA_CboCategory.SelectionChanged += self.FA_Category_Changed

    def FA_Scan_Click(self, sender, args):
        self.SetLoading(True, "Scanning families...")
        try:
            raw = _fa_logic.collect_families(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Error scanning families: {}".format(e))
            return

        self._fa_all_rows = [FA_FamilyRow(r) for r in raw]

        cats = sorted(set(r.Category for r in self._fa_all_rows))
        self.FA_CboCategory.ItemsSource   = [_FA_ALL_CATS] + cats
        self.FA_CboCategory.SelectedIndex = 0

        self.SetLoading(False)
        self._fa_apply_filters()

        self.FA_BtnExport.IsEnabled = True
        self.FA_TxtFamilyCount.Text = "{} families loaded".format(len(self._fa_all_rows))

    def FA_Filter_Changed(self, sender, args):
        self._fa_apply_filters()

    def FA_Category_Changed(self, sender, args):
        if not getattr(self, '_is_loaded', False):
            return
        self._fa_apply_filters()

    def _fa_apply_filters(self):
        cat_sel      = self.FA_CboCategory.SelectedItem
        only_unused  = self.FA_ChkOnlyUnused.IsChecked    == True
        only_edit    = self.FA_ChkOnlyEditable.IsChecked  == True
        only_incomplete = self.FA_ChkOnlyIncomplete.IsChecked == True
        search_txt   = (self.FA_TxtSearch.Text or '').strip().lower()
        if search_txt == _FA_SEARCH_PH.lower():
            search_txt = ''

        visible = []
        for row in self._fa_all_rows:
            if cat_sel and cat_sel != _FA_ALL_CATS and row.Category != cat_sel:
                continue
            if only_unused and not row.IsUnused:
                continue
            if only_edit and row.Editable != 'Yes':
                continue
            if only_incomplete and row._raw['completeness'] >= 1.0:
                continue
            if search_txt and search_txt not in row.Name.lower() \
                          and search_txt not in row.Category.lower():
                continue
            visible.append(row)

        self._fa_rows.Clear()
        for row in visible:
            self._fa_rows.Add(row)

        self._fa_update_pills()

    def FA_Search_GotFocus(self, sender, args):
        if self.FA_TxtSearch.Text == _FA_SEARCH_PH:
            self.FA_TxtSearch.Text = ''
            self.FA_TxtSearch.Foreground = System.Windows.Media.Brushes.Black
            self._fa_search_on = True

    def FA_Search_LostFocus(self, sender, args):
        if not self.FA_TxtSearch.Text.strip():
            self.FA_TxtSearch.Text = _FA_SEARCH_PH
            self.FA_TxtSearch.Foreground = System.Windows.Media.Brushes.Gray
            self._fa_search_on = False

    def FA_Search_Changed(self, sender, args):
        if self._fa_search_on or self.FA_TxtSearch.Text != _FA_SEARCH_PH:
            self._fa_apply_filters()

    def FA_RowCheck_Click(self, sender, args):
        self._fa_update_pills()

    def FA_CheckAll_Click(self, sender, args):
        for row in self._fa_rows:
            row.IsChecked = True
        self.FA_GridFamilies.Items.Refresh()
        self._fa_update_pills()

    def FA_CheckNone_Click(self, sender, args):
        for row in self._fa_rows:
            row.IsChecked = False
        self.FA_GridFamilies.Items.Refresh()
        self._fa_update_pills()

    def _fa_update_pills(self):
        total     = len(self._fa_rows)
        unused    = sum(1 for r in self._fa_rows if r.IsUnused)
        checked   = sum(1 for r in self._fa_rows if r.IsChecked)
        instances = sum(r.InstanceCount for r in self._fa_rows)

        self.FA_TxtPillTotal.Text     = "{} families".format(total)
        self.FA_TxtPillUnused.Text    = "{} unused".format(unused)
        self.FA_TxtPillSelected.Text  = "{} checked".format(checked)
        self.FA_TxtPillInstances.Text = "{} instances".format(instances)

        self.FA_BtnPurge.IsEnabled  = checked > 0
        self.FA_BtnSelect.IsEnabled = self.FA_GridFamilies.SelectedItem is not None

    def FA_Grid_SelectionChanged(self, sender, args):
        self.FA_BtnSelect.IsEnabled = self.FA_GridFamilies.SelectedItem is not None

    def FA_Purge_Click(self, sender, args):
        checked = [r for r in self._fa_rows if r.IsChecked]
        if not checked:
            return

        names = '\n'.join('  • ' + r.Name for r in checked[:10])
        if len(checked) > 10:
            names += '\n  ...and {} more'.format(len(checked) - 10)

        if not forms.alert(
            "Permanently delete {} family(ies) from the project?\n\n{}".format(
                len(checked), names),
            yes=True, no=True
        ):
            return

        fids = [r.Id for r in checked]
        self.SetLoading(True, "Purging...")
        try:
            deleted, failed = _fa_logic.purge_families(self.doc, fids)
        except Exception as e:
            self.SetLoading(False)
            forms.alert("Purge failed: {}".format(e))
            return

        self.SetLoading(False)
        forms.alert("Deleted: {}  |  Failed: {}".format(deleted, len(failed)),
                    title="Purge Complete")
        self.FA_Scan_Click(None, None)

    def FA_SelectInModel_Click(self, sender, args):
        row = self.FA_GridFamilies.SelectedItem
        if row is None:
            return
        type_ids = set(get_id_value(tid) for tid in row._family.GetFamilySymbolIds())
        col = DB.FilteredElementCollector(self.doc)\
                 .WhereElementIsNotElementType()\
                 .OfClass(DB.FamilyInstance)\
                 .ToElements()
        ids = [inst.Id for inst in col
               if inst.Symbol and get_id_value(inst.Symbol.Id) in type_ids]
        if ids:
            from pyrevit import revit as _rv
            _rv.get_selection().set_to(ids)
            forms.alert("Selected {} instance(s) of '{}'.".format(len(ids), row.Name))
        else:
            forms.alert("No instances of '{}' found in model.".format(row.Name))

    def FA_Export_Click(self, sender, args):
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            raw = [r._raw for r in self._fa_rows]
            _fa_logic.export_to_csv(raw, path)
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 4: IFC STRUCTURAL EXPORT QA
    # ══════════════════════════════════════════════════════════════════

    def _iq_init(self):
        self._iq_run_checks()

    def _iq_run_checks(self):
        self.SetLoading(True, u'Running IFC QA checks…')
        try:
            results = _iq_logic.run_all_checks(self.doc)
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e))
            return
        self.SetLoading(False)
        self._iq_render(results)

    def _iq_render(self, results):
        import System.Windows.Controls as WC
        import System.Windows.Media as Media

        panel = self.IQ_ResultsPanel
        panel.Children.Clear()

        for r in results:
            card = WC.Border()
            card.CornerRadius = System.Windows.CornerRadius(6)
            card.Padding = System.Windows.Thickness(12, 10, 12, 10)
            card.Margin = System.Windows.Thickness(0, 0, 0, 8)
            card.Background = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(
                    {'green': '#f0fdf4', 'amber': '#fffbeb', 'red': '#fef2f2'}[r.status]))

            sp = WC.StackPanel()
            hdr = WC.TextBlock()
            hdr.Text = u'{} — {} issue(s)'.format(r.check_name, r.count)
            hdr.FontWeight = System.Windows.FontWeights.SemiBold
            hdr.Foreground = Media.SolidColorBrush(
                Media.ColorConverter.ConvertFromString(_IQ_STATUS_COLOUR[r.status]))
            sp.Children.Add(hdr)
            for line in r.detail[:8]:
                tb = WC.TextBlock()
                tb.Text = u'  · ' + line
                tb.FontSize = 10
                tb.TextWrapping = System.Windows.TextWrapping.Wrap
                sp.Children.Add(tb)
            card.Child = sp
            panel.Children.Add(card)

    def IQ_Refresh_Click(self, sender, args):
        self._iq_run_checks()

    # ══════════════════════════════════════════════════════════════════
    # TAB 5: SCHEDULE IMPACT
    # ══════════════════════════════════════════════════════════════════

    def _si_init(self):
        self._si_rows = ObservableCollection[object]()
        self._si_cats = []
        self.SI_ImpactGrid.ItemsSource = self._si_rows
        self._si_load_categories()

    def _si_load_categories(self):
        self.SI_CboCategory.Items.Clear()
        self._si_cats = _si_logic.get_schedulable_categories(self.doc)
        for name, cat in self._si_cats:
            self.SI_CboCategory.Items.Add(name)
        if self._si_cats:
            self.SI_CboCategory.SelectedIndex = 0
        self.SI_TxtResult.Text = u'{} schedulable categories found.'.format(len(self._si_cats))

    def SI_Analyse_Click(self, sender, args):
        idx = self.SI_CboCategory.SelectedIndex
        if idx < 0 or idx >= len(self._si_cats):
            forms.alert(u'Select a category first.', title=u'Schedule Impact')
            return
        _, cat = self._si_cats[idx]
        self.SetLoading(True, u'Analysing schedules…')
        try:
            records = _si_logic.analyse(self.doc, get_id_value(cat.Id))
        except Exception as e:
            self.SetLoading(False)
            forms.alert(u'Error:\n{}'.format(e), title=u'Schedule Impact')
            return
        self._si_all_rows = [SI_ImpactRow(r) for r in records]
        self._si_apply_search()
        self.SetLoading(False)
        total_sheets = sum(r.get('sheet_count', 0) for r in records)
        self.SI_TxtResult.Text = u'{} schedule{} found, placed on {} sheet{}.'.format(
            len(records), u's' if len(records) != 1 else u'',
            total_sheets, u's' if total_sheets != 1 else u'')

    def _si_apply_search(self):
        try:
            text = (self.SI_TxtSearch.Text or u'').strip().lower()
        except Exception:
            text = u''
        self._si_rows.Clear()
        for row in getattr(self, '_si_all_rows', []):
            if text and text not in row.ScheduleName.lower() \
                    and text not in row.Sheets.lower():
                continue
            self._si_rows.Add(row)

    def SI_Search_Changed(self, sender, args):
        self._si_apply_search()

    def SI_ExportCsv_Click(self, sender, args):
        rows = list(self._si_rows)
        if not rows:
            forms.alert(u'Run an analysis first.', title=u'Schedule Impact')
            return
        try:
            from nosa_utils.export_io import save_csv
            path = save_csv(
                [u'Schedule', u'Fields', u'Sheet count', u'Sheets'],
                [[r.ScheduleName, r.FieldCount, r.SheetCount, r.Sheets] for r in rows],
                default_name=u'schedule_impact')
            if path:
                self.SI_TxtResult.Text = u'Exported to: {}'.format(path)
        except Exception as e:
            forms.alert(u'Export failed:\n{}'.format(e), title=u'Schedule Impact')

    def SI_Grid_DoubleClick(self, sender, args):
        row = self.SI_ImpactGrid.SelectedItem
        if row is None or not getattr(row, 'ScheduleId', 0):
            return
        try:
            from pyrevit import revit
            from nosa_utils.revit_helpers import element_id_from_int
            view = self.doc.GetElement(element_id_from_int(row.ScheduleId))
            if view is not None:
                revit.uidoc.RequestViewChange(view)
                self.SI_TxtResult.Text = u'Opening schedule "{}"…'.format(row.ScheduleName)
        except Exception as e:
            self.SI_TxtResult.Text = u'Could not open schedule: {}'.format(e)

    # ══════════════════════════════════════════════════════════════════
    # TAB 6: REBAR COVERAGE
    # ══════════════════════════════════════════════════════════════════

    def _rc_init(self):
        self._rc_data = None
        self._rc_missing = ObservableCollection[RC_MissingRow]()
        self._rc_summary = ObservableCollection[RC_SummaryRow]()
        self.RC_GridMissing.ItemsSource = self._rc_missing
        self.RC_GridSummary.ItemsSource = self._rc_summary

    def _rc_selected_cats(self):
        cats = []
        m = {'Structural Columns': self.RC_ChkColumns,
             'Structural Framing': self.RC_ChkFraming,
             'Structural Foundations': self.RC_ChkFoundations,
             'Floors': self.RC_ChkFloors, 'Walls': self.RC_ChkWalls}
        return [c for c, cb in m.items() if cb.IsChecked == True] or None

    def RC_Run_Click(self, sender, args):
        self.SetLoading(True, 'Checking rebar coverage...')
        self._rc_missing.Clear(); self._rc_summary.Clear()
        self.RC_BtnExport.IsEnabled = False
        try:
            self._rc_data = _rc_logic.check_rebar_coverage(self.doc, self._rc_selected_cats())
        except Exception as e:
            self.SetLoading(False); forms.alert('Error: {}'.format(e)); return

        pct = self._rc_data['coverage_pct']
        self.RC_CoverageBar.Value = pct
        self.RC_TxtCoverage.Text  = "{}%".format(int(round(pct)))

        if pct >= 90:
            self.RC_CoverageBar.Foreground = System.Windows.Media.Brushes.SeaGreen
            self.RC_TxtCoverageLabel.Text = "Excellent — almost all elements have rebar."
        elif pct >= 70:
            self.RC_CoverageBar.Foreground = System.Windows.Media.SolidColorBrush(
                System.Windows.Media.Color.FromRgb(255,95,0))
            self.RC_TxtCoverageLabel.Text = "Good — some elements are missing rebar."
        else:
            self.RC_CoverageBar.Foreground = System.Windows.Media.Brushes.Crimson
            self.RC_TxtCoverageLabel.Text = "Poor — many structural elements have no rebar."

        for s in self._rc_data['summary']:
            self._rc_summary.Add(RC_SummaryRow(s))
        for r in self._rc_data['without_rebar']:
            self._rc_missing.Add(RC_MissingRow(r))

        n = len(self._rc_data['without_rebar'])
        self.RC_TxtMissingLabel.Text = "{} elements without rebar".format(n)
        self.SetLoading(False)
        self.RC_BtnExport.IsEnabled = True

    def RC_Grid_SelectionChanged(self, sender, args):
        self.RC_BtnSelect.IsEnabled = self.RC_GridMissing.SelectedItem is not None

    def RC_Select_Click(self, sender, args):
        rows = list(self.RC_GridMissing.SelectedItems)
        if not rows: return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([element_id_from_int(r.Id) for r in rows])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert('Could not select: {}'.format(e))

    def RC_Export_Click(self, sender, args):
        if not self._rc_data: return
        path = forms.save_file(file_ext='csv')
        if not path: return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['Coverage', '{}%'.format(self._rc_data['coverage_pct'])])
                w.writerow([])
                w.writerow(['Category','With rebar','Without rebar','Coverage %'])
                for r in self._rc_summary:
                    w.writerow([r.Category, r.WithRebar, r.WithoutRebar, r.Coverage])
                w.writerow([])
                w.writerow(['Category','Level','Name','ID'])
                for r in self._rc_missing:
                    w.writerow([r.Category, r.Level, r.Name, r.Id])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # TAB 7: QUANTIFICATION QA
    # ══════════════════════════════════════════════════════════════════

    def _qq_init(self):
        self._qq_data = None
        self._qq_tabs = {
            'QQ_BtnTabConcrete': self.QQ_TabConcrete,
            'QQ_BtnTabSteel':    self.QQ_TabSteel,
            'QQ_BtnTabRebar':    self.QQ_TabRebar,
            'QQ_BtnTabQA':       self.QQ_TabQA,
        }
        self._qq_quant_rows = ObservableCollection[QQ_QuantRow]()
        self._qq_steel_rows = ObservableCollection[QQ_SteelRow]()
        self._qq_rebar_rows = ObservableCollection[QQ_RebarRow]()
        self._qq_qa_rows    = ObservableCollection[QQ_QARow]()
        self.QQ_GridConcrete.ItemsSource = self._qq_quant_rows
        self.QQ_GridSteel.ItemsSource    = self._qq_steel_rows
        self.QQ_GridRebar.ItemsSource    = self._qq_rebar_rows
        self.QQ_GridQA.ItemsSource       = self._qq_qa_rows
        self._qq_load_filters()

    def _qq_load_filters(self):
        try:
            cats     = _qq_logic.get_available_categories()
            levels   = _qq_logic.get_available_levels(self.doc)
            families = _qq_logic.get_all_family_names(self.doc)
            self.QQ_ListCats.ItemsSource            = cats
            self.QQ_ListLevels.ItemsSource          = levels
            self.QQ_ListExcludeFamilies.ItemsSource = families
            self.QQ_ListCats.SelectAll()
            self.QQ_ListLevels.SelectAll()
        except Exception as e:
            logger.debug('QuantQA _load_filters: {}'.format(e))

    def _qq_selected_cats(self):
        return [str(i) for i in self.QQ_ListCats.SelectedItems] or None

    def _qq_selected_levels(self):
        return [str(i) for i in self.QQ_ListLevels.SelectedItems] or None

    def _qq_excluded_families(self):
        items = self.QQ_ListExcludeFamilies.SelectedItems
        return [str(i) for i in items] if items else None

    def QQ_SelectAll_Click(self, sender, args):
        self.QQ_ListCats.SelectAll()
        self.QQ_ListLevels.SelectAll()

    def QQ_NavButton_Click(self, sender, args):
        self.SwitchTab(sender.Name, self._qq_tabs)

    def _qq_run_analysis(self, excluded_families=None):
        self.SetLoading(True, 'Calculating quantities...')
        self._qq_quant_rows.Clear()
        self._qq_steel_rows.Clear()
        self._qq_rebar_rows.Clear()
        self._qq_qa_rows.Clear()
        self.QQ_BtnExport.IsEnabled = False
        try:
            excl_phase = getattr(self, 'QQ_ChkExcludeExisting', None)
            excl_piles = getattr(self, 'QQ_ChkExcludePiles', None)
            self._qq_data = _qq_logic.run_all(
                self.doc,
                self._qq_selected_cats(),
                self._qq_selected_levels(),
                excluded_families,
                exclude_existing_phase=(excl_phase is not None and excl_phase.IsChecked == True),
                exclude_piles=(excl_piles is not None and excl_piles.IsChecked == True),
            )
        except Exception as e:
            self.SetLoading(False)
            forms.alert('Error: {}'.format(e))
            return

        for r in self._qq_data['agg_concrete']:
            self._qq_quant_rows.Add(QQ_QuantRow(r))
        for r in self._qq_data['agg_steel']:
            self._qq_steel_rows.Add(QQ_SteelRow(r))
        for r in self._qq_data['agg_rebar']:
            self._qq_rebar_rows.Add(QQ_RebarRow(r))
        for r in self._qq_data['qa_issues']:
            self._qq_qa_rows.Add(QQ_QARow(r))

        t = self._qq_data['totals']
        self.QQ_TxtTotalVol.Text   = 'Concrete: {:.2f} m³'.format(t['volume_m3'])
        self.QQ_TxtTotalSteel.Text = 'Steel: {:.0f} kg'.format(t['steel_kg'])
        self.QQ_TxtTotalRebar.Text = 'Rebar: {:.0f} kg'.format(t['rebar_kg'])
        qa_n = t['qa_issues']
        self.QQ_TxtQACount.Text    = '{} QA issues'.format(qa_n) if qa_n else ''

        self.SetLoading(False)
        self.QQ_BtnExport.IsEnabled = True

    def QQ_Run_Click(self, sender, args):
        self._qq_run_analysis(self._qq_excluded_families())

    def QQ_ApplyExclusion_Click(self, sender, args):
        self._qq_run_analysis(self._qq_excluded_families())

    def QQ_QAGrid_SelectionChanged(self, sender, args):
        rows = list(self.QQ_GridQA.SelectedItems) if self.QQ_GridQA.SelectedItems else []
        has  = len(rows) > 0
        self.QQ_BtnQASelect.IsEnabled       = has
        self.QQ_BtnAssignMaterial.IsEnabled = has
        self.QQ_TxtQASelection.Text = "{} selected".format(len(rows)) if rows else ""

    def QQ_QASelect_Click(self, sender, args):
        rows = list(self.QQ_GridQA.SelectedItems) if self.QQ_GridQA.SelectedItems else []
        if not rows:
            return
        try:
            from System.Collections.Generic import List
            ids = List[DB.ElementId]([element_id_from_int(r.Id) for r in rows if r.Id])
            revit.uidoc.Selection.SetElementIds(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def QQ_AssignMaterial_Click(self, sender, args):
        """Assign a material to QA-selected elements with missing material."""
        rows = [r for r in (self.QQ_GridQA.SelectedItems or []) if r.Id]
        if not rows:
            return
        try:
            mats = sorted(
                DB.FilteredElementCollector(self.doc).OfClass(DB.Material).ToElements(),
                key=lambda m: m.Name
            )
            if not mats:
                forms.alert("No materials found in the project.")
                return
            chosen = forms.SelectFromList.show(
                [m.Name for m in mats], title="Select material to assign", button_name="Assign"
            )
            if not chosen:
                return
            mat = next((m for m in mats if m.Name == chosen), None)
            if not mat:
                return
            ok = fail = 0
            with revit.Transaction("NOSA — Assign Material"):
                for row in rows:
                    assigned = False
                    try:
                        el = self.doc.GetElement(element_id_from_int(row.Id))
                        if not el:
                            fail += 1
                            continue
                        p = el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                        if p and not p.IsReadOnly:
                            p.Set(mat.Id)
                            ok += 1
                            continue
                        try:
                            type_id = el.GetTypeId()
                            if type_id and type_id != DB.ElementId.InvalidElementId:
                                type_el = self.doc.GetElement(type_id)
                                if type_el:
                                    tp = type_el.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
                                    if tp and not tp.IsReadOnly:
                                        tp.Set(mat.Id)
                                        ok += 1
                                        assigned = True
                        except Exception:
                            log_swallowed(_LOG, u'QQ_AssignMaterial_Click')
                        if not assigned:
                            fail += 1
                    except Exception:
                        fail += 1
            forms.alert("Material '{}' assigned.\n\nUpdated: {}\nFailed: {}".format(chosen, ok, fail))
        except Exception as e:
            forms.alert("Error: {}".format(e))

    def QQ_Export_Click(self, sender, args):
        if not self._qq_data:
            return
        path = forms.save_file(file_ext='csv')
        if not path:
            return
        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                w = csv.writer(f)
                w.writerow(['=== CONCRETE QUANTITIES ==='])
                w.writerow(['Category', 'Material', 'Level', 'Volume m3', 'Area m2', 'Count'])
                for r in self._qq_quant_rows:
                    w.writerow([r.Category, r.Material, r.Level, r.VolStr, r.AreaStr, r.Count])
                w.writerow([])
                w.writerow(['=== STEEL QUANTITIES ==='])
                w.writerow(['Category', 'Material', 'Level', 'Weight kg', 'Weight t', 'Count'])
                for r in self._qq_steel_rows:
                    w.writerow([r.Category, r.Material, r.Level, r.WeightKg, r.WeightTonne, r.Count])
                w.writerow([])
                w.writerow(['=== REBAR ==='])
                w.writerow(['Level', 'Diameter mm', 'Count', 'Total length m', 'Weight kg'])
                for r in self._qq_rebar_rows:
                    w.writerow([r.Level, r.DiamStr, r.Count, r.LengthStr, r.WeightStr])
                w.writerow([])
                w.writerow(['=== QA ISSUES ==='])
                w.writerow(['Severity', 'Category', 'Level', 'Element', 'Problem'])
                for r in self._qq_qa_rows:
                    w.writerow([r.Severity, r.Category, r.Level, r.Name, r.Problem])
            forms.alert('Exported to:\n{}'.format(path))
        except Exception as e:
            forms.alert('Export failed: {}'.format(e))

    # ══════════════════════════════════════════════════════════════════
    # Shared
    # ══════════════════════════════════════════════════════════════════

    def Theme_Toggled(self, sender, args):
        NOSAWindow.Theme_Toggled(self, sender, args)
        cfg = self.LoadConfig()
        cfg['dark_mode'] = self.dark_mode
        self.SaveConfig(cfg)
