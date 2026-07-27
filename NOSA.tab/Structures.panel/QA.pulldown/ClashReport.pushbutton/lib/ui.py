# -*- coding: utf-8 -*-
import imp
import io
import os, sys, csv
import System.Windows
from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from Autodesk.Revit import DB
from pyrevit import forms, revit

_lib = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..', 'lib'))
if _lib not in sys.path:
    sys.path.insert(0, _lib)

from nosa_utils.base_window import NOSAWindow
_logic_mod = imp.load_source('clashreport_logic', os.path.join(os.path.dirname(__file__), 'logic.py'))
ClashLogic  = _logic_mod.ClashLogic


class CategoryItem(object):
    def __init__(self, name, category, count):
        self.Name     = "{} ({})".format(name, count)
        self.Category = category
        self.RawName  = name
        self.Count    = count
        self.IsChecked = False


class ClashResultItem(object):
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


_STRUCTURAL_CATS = None


def _structural_cats():
    global _STRUCTURAL_CATS
    if _STRUCTURAL_CATS is None:
        _STRUCTURAL_CATS = [
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
    return _STRUCTURAL_CATS


class ClashReportWindow(NOSAWindow):

    def __init__(self, doc):
        xaml = os.path.join(os.path.dirname(__file__), 'ui.xaml')
        NOSAWindow.__init__(self, xaml, 'clash_report')
        self.doc   = doc
        self.logic = ClashLogic(doc)

        self._categories = ObservableCollection[CategoryItem]()
        self._results    = ObservableCollection[ClashResultItem]()
        self.ListCategories.ItemsSource = self._categories
        self.GridResults.ItemsSource    = self._results

        cfg = self.LoadConfig()
        self.ChkDarkMode.IsChecked = cfg.get('dark_mode', self.dark_mode)

        self._load_categories()

    # ── load categories ───────────────────────────────────────────────────────

    def _load_categories(self):
        for name, cat in _structural_cats():
            elements = self.logic.collect_elements_by_category(cat)
            if elements:
                self._categories.Add(CategoryItem(name, cat, len(elements)))

    # ── run check ─────────────────────────────────────────────────────────────

    def Run_Click(self, sender, args):
        selected = list(self.ListCategories.SelectedItems) if self.ListCategories.SelectedItems else []
        if len(selected) < 2:
            forms.alert("Select at least 2 categories to check.")
            return

        # Pre-run size warning: pairwise comparisons across selected categories
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
        self._results.Clear()
        self.TxtSummary.Text = ""
        self.BtnExportCSV.IsEnabled  = False
        self.BtnExportHTML.IsEnabled = False
        self.BtnExportBCF.IsEnabled  = False

        try:
            self._run_clash_check(selected)
        except Exception as e:
            forms.alert("Error during clash check: {}".format(e))
        finally:
            self.SetLoading(False)

        self.BtnExportCSV.IsEnabled  = len(self._results) > 0
        self.BtnExportHTML.IsEnabled = len(self._results) > 0
        self.BtnExportBCF.IsEnabled  = len(self._results) > 0

    def _run_clash_check(self, selected_cats):
        self.logic.clear_solid_cache()
        all_elements = []
        for cat_item in selected_cats:
            self.SetLoading(True, "Collecting {}...".format(cat_item.RawName))
            elements = self.logic.collect_elements_by_category(cat_item.Category)
            for el in elements:
                bbox = self.logic.get_element_bounding_box(el)
                if bbox:
                    all_elements.append((el, bbox, cat_item.RawName))

        total = len(all_elements)
        self.SetLoading(True, "Checking {} elements...".format(total))

        clashes    = []
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
                    self.logic.get_id_value(elem1.Id),
                    self.logic.get_id_value(elem2.Id)
                ]))
                if pair_key in clash_pairs:
                    continue
                if not self.logic.bounding_boxes_intersect(bbox1, bbox2):
                    continue
                solid1 = self.logic.get_element_solid_cached(elem1)
                solid2 = self.logic.get_element_solid_cached(elem2)
                if solid1 and solid2:
                    vol = self.logic.intersect_volume(solid1, solid2)
                    if vol > 0:
                        clash_pairs.add(pair_key)
                        info1 = self.logic.get_element_info(elem1)
                        info2 = self.logic.get_element_info(elem2)
                        clashes.append((info1, info2, vol))

        for idx, clash in enumerate(clashes):
            vol = clash[2] if len(clash) > 2 else 0.0
            self._results.Add(ClashResultItem(idx + 1, clash, vol))

        high   = sum(1 for r in self._results if r.Severity == 'High')
        medium = sum(1 for r in self._results if r.Severity == 'Medium')
        low    = sum(1 for r in self._results if r.Severity == 'Low')
        self.TxtSummary.Text = "{} clashes — {} High  {} Medium  {} Low".format(
            len(clashes), high, medium, low)

    # ── grid actions ─────────────────────────────────────────────────────────

    def Grid_SelectionChanged(self, sender, args):
        has = self.GridResults.SelectedItem is not None
        self.BtnIsolate.IsEnabled   = has
        self.BtnSelectBoth.IsEnabled = has

    def SelectBoth_Click(self, sender, args):
        item = self.GridResults.SelectedItem
        if not item:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(int(item.Id1)),
                                      DB.ElementId(int(item.Id2))])
            revit.uidoc.Selection.SetElementIds(ids)
            try:
                revit.uidoc.ShowElements(ids)
            except Exception:
                pass
        except Exception as e:
            forms.alert("Could not select: {}".format(e))

    def Isolate_Click(self, sender, args):
        item = self.GridResults.SelectedItem
        if not item:
            return
        try:
            ids = List[DB.ElementId]([DB.ElementId(int(item.Id1)),
                                      DB.ElementId(int(item.Id2))])
            with revit.Transaction("Isolate Clash"):
                revit.active_view.IsolateElementsTemporary(ids)
            revit.uidoc.ShowElements(ids)
        except Exception as e:
            forms.alert("Error isolating: {}".format(e))

    # ── export CSV ────────────────────────────────────────────────────────────

    def ExportCSV_Click(self, sender, args):
        if not self._results:
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
                for r in self._results:
                    w.writerow([r.Index, r.Severity, r.VolumeStr,
                                r.Name1, r.Cat1, r.Id1,
                                r.Name2, r.Cat2, r.Id2])
            forms.alert("Exported:\n{}".format(path))
        except Exception as e:
            forms.alert("Export failed: {}".format(e))

    # ── export HTML ───────────────────────────────────────────────────────────

    def ExportHTML_Click(self, sender, args):
        if not self._results:
            return
        path = forms.save_file(file_ext='html')
        if not path:
            return

        from collections import Counter
        pair_counts = Counter()
        for item in self._results:
            key = tuple(sorted([item.Cat1, item.Cat2]))
            pair_counts[key] += 1

        sev_color = {'High': '#FFDDDD', 'Medium': '#FFE8CC', 'Low': '#F5F5F5'}
        rows_html = ''
        for item in self._results:
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
        ).format(total=len(list(self._results)), summary=summary_rows, rows=rows_html)

        try:
            with io.open(path, 'w', encoding='utf-8-sig', newline='') as f:
                f.write(html)
            import subprocess
            subprocess.Popen(['start', path], shell=True)
        except Exception as e:
            forms.alert("Export error: {}".format(e))

    # ── export BCF 2.1 ────────────────────────────────────────────────────────

    def ExportBCF_Click(self, sender, args):
        if not self._results:
            return
        path = forms.save_file(file_ext='bcf')
        if not path:
            return
        if not path.lower().endswith('.bcf'):
            path += '.bcf'
        try:
            self._write_bcf(path)
            forms.alert("BCF 2.1 exported:\n{}".format(path))
        except Exception as e:
            forms.alert("BCF export failed: {}".format(e))

    def _write_bcf(self, bcf_path):
        import zipfile, uuid, datetime
        now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

        with zipfile.ZipFile(bcf_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # BCF version file
            zf.writestr('bcf.version', (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Version VersionId="2.1" xsi:noNamespaceSchemaLocation="version.xsd"'
                ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                '<DetailedVersion>2.1</DetailedVersion></Version>'
            ))

            for item in self._results:
                topic_id = str(uuid.uuid4())
                folder = topic_id + '/'

                # markup.bcf
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

                # viewpoint.bcfv (minimal — no camera, just element references)
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
