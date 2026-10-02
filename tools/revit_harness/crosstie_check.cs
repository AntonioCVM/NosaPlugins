// Live check of RebarAutomate column crossties (rvt-mcp revit_send_code_to_revit body).
// Test models only (guarded by title). Creates 3 concrete columns away from the model
// (400x400 / 8 bars -> interior diamond loop, 400x600 / 12 and 600x600 / 16 -> straight
// crossties), reinforces them through ra_harness.py with crossties on, and reports per column:
// rebar count by layer, crosstie hooks, where each crosstie end sits relative to the nearest
// vertical bar, and new Revit warnings. EXT points at the checkout to test.
var allowed = new[] { "Rebar test", "Project1", "Project2", "Project3" };
if (!allowed.Contains(doc.Title)) return "ABORT: not a test model (" + doc.Title + ")";
string EXT = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData)
    + @"\pyRevit\Extensions\NOSA.extension\.claude\worktrees\sweet-jemison-1f1a79";
const double MM = 1.0 / 304.8;
var sb = new System.Text.StringBuilder(doc.Application.VersionNumber + " " + doc.Title + "\n");
int warnings0 = doc.GetWarnings().Count;

var level = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>().OrderBy(l => l.Elevation).First();
var baseSym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).OfCategory(BuiltInCategory.OST_StructuralColumns)
    .Cast<FamilySymbol>().FirstOrDefault(s => s.Family.StructuralMaterialType == StructuralMaterialType.Concrete
        && s.LookupParameter("b") != null && s.LookupParameter("h") != null);
if (baseSym == null) return "ABORT: no concrete rectangular column type with b/h";

var cases = new[] { new { b = 400, h = 400, n = 8 }, new { b = 400, h = 600, n = 12 }, new { b = 600, h = 600, n = 16 } };
var ids = new List<ElementId>();
using (var t = new Transaction(doc, "NOSA test - crosstie columns")) {
    t.Start();
    int i = 0;
    foreach (var c in cases) {
        string name = "NOSA TEST " + c.b + "x" + c.h;
        var sym = new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).Cast<FamilySymbol>()
            .FirstOrDefault(s => s.Family.Id == baseSym.Family.Id && s.Name == name)
            ?? (FamilySymbol)baseSym.Duplicate(name);
        sym.LookupParameter("b").Set(c.b * MM);
        sym.LookupParameter("h").Set(c.h * MM);
        if (!sym.IsActive) sym.Activate();
        var col = doc.Create.NewFamilyInstance(new XYZ((200000 + 3000 * i) * MM, 200000 * MM, level.Elevation),
            sym, level, Autodesk.Revit.DB.Structure.StructuralType.Column);
        col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(level.Id);
        col.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(3000 * MM);
        ids.Add(col.Id);
        i++;
    }
    t.Commit();
}

var asm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "pyRevitLoader");
var et = asm.GetType("PyRevitLoader.ScriptExecutor");
dynamic exec = et.GetConstructors().First().Invoke(null);
for (int k = 0; k < cases.Length; k++) {
    dynamic engine = et.GetMethod("CreateEngine").Invoke(exec, null);
    et.GetMethod("AddEmbeddedLib").Invoke(exec, new object[] { engine });
    dynamic scope = engine.CreateScope();
    scope.SetVariable("doc", doc); scope.SetVariable("MODE", "columns");
    scope.SetVariable("IDS", new long[] { ids[k].Value });
    scope.SetVariable("CONTROLS", "{\"ChkColCrossties\": true, \"TxtColBarCount\": \"" + cases[k].n + "\"}");
    scope.SetVariable("OVERRIDES", "{}"); scope.SetVariable("EXT_ROOT", EXT);
    scope.SetVariable("PYREVIT", Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit-Master");
    engine.ExecuteFile(EXT + @"\tools\revit_harness\ra_harness.py", scope);
    string res = (string)scope.GetVariable("RESULT");
    sb.AppendLine("== column " + cases[k].b + "x" + cases[k].h + " / " + cases[k].n + " bars (id " + ids[k].Value + ")");
    sb.AppendLine("   harness: " + string.Join(" / ", res.Split('\n').Where(l => l.Contains("ALERT") || l.Contains("EXCEPTION")
        || l.Contains("rror") || l.Contains("crosstie") || l.Contains("interior")).Take(8)));

    var host = doc.GetElement(ids[k]);
    var rebars = Autodesk.Revit.DB.Structure.RebarHostData.GetRebarHostData(host).GetRebarsInHost()
        .Cast<Autodesk.Revit.DB.Structure.Rebar>().ToList();
    Func<Autodesk.Revit.DB.Structure.Rebar, string> layer = r => {
        var p = r.LookupParameter("NOSA_Rebar_Layer"); var s = p == null ? null : p.AsString();
        if (!string.IsNullOrEmpty(s)) return s;
        var cs = r.GetCenterlineCurves(false, true, true, MultiplanarOption.IncludeOnlyPlanarCurves, 0);
        var longest = cs.OrderByDescending(c => c.Length).First();
        if (Math.Abs(longest.GetEndPoint(0).Z - longest.GetEndPoint(1).Z) > 0.5 * longest.Length) return "vertical";
        bool closed = cs.First().GetEndPoint(0).DistanceTo(cs.Last().GetEndPoint(1)) < 0.05;
        if (closed || cs.Count >= 4) return "stirrup";
        return "crosstie"; };
    sb.AppendLine("   rebars: " + string.Join(", ", rebars.GroupBy(layer).Select(g => g.Key + "=" + g.Count()
        + "(" + g.Sum(r => r.Quantity) + " bars)")));

    // vertical bar centrelines in plan
    var verts = new List<XYZ>();
    foreach (var r in rebars.Where(r => layer(r) == "vertical")) {
        for (int bi = 0; bi < r.NumberOfBarPositions; bi++)
            foreach (var cv in r.GetTransformedCenterlineCurves(false, true, true, MultiplanarOption.IncludeOnlyPlanarCurves, bi))
                if (Math.Abs(cv.GetEndPoint(0).Z - cv.GetEndPoint(1).Z) > 1) verts.Add(new XYZ(cv.GetEndPoint(0).X, cv.GetEndPoint(0).Y, 0));
    }
    foreach (var r in rebars.Where(r => layer(r) == "crosstie" || layer(r) == "interior_stirrup").Take(2)) {
        var hs = r.GetHookTypeId(0); var he = r.GetHookTypeId(1);
        Func<ElementId, string> hookName = id => id == ElementId.InvalidElementId ? "none"
            : Math.Round(((Autodesk.Revit.DB.Structure.RebarHookType)doc.GetElement(id)).HookAngle * 180 / Math.PI) + "deg";
        var curves = r.GetCenterlineCurves(false, true, true, MultiplanarOption.IncludeOnlyPlanarCurves, 0);
        var straight = curves.OrderByDescending(c => c.Length).First();
        double dia = r.LookupParameter("Bar Diameter") != null ? r.LookupParameter("Bar Diameter").AsDouble() / MM : 0;
        string ends = string.Join(" ; ", new[] { straight.GetEndPoint(0), straight.GetEndPoint(1) }.Select(p => {
            var pp = new XYZ(p.X, p.Y, 0);
            double d = verts.Count == 0 ? -1 : verts.Min(v => v.DistanceTo(pp)) / MM;
            return "end->nearest vertical axis " + Math.Round(d, 1) + "mm";
        }));
        sb.AppendLine("   " + layer(r) + ": shape=" + doc.GetElement(r.GetShapeId()).Name + " hooks " + hookName(hs) + "/" + hookName(he)
            + " dia=" + Math.Round(dia) + " straight=" + Math.Round(straight.Length / MM) + "mm segs=" + curves.Count
            + " qty=" + r.Quantity + " | " + ends);
    }
}
var newWarnings = doc.GetWarnings().Skip(warnings0).Select(w => w.GetDescriptionText()).GroupBy(s => s)
    .Select(g => g.Count() + "x " + g.Key);
sb.AppendLine("new warnings: " + doc.GetWarnings().Count + " total, +" + (doc.GetWarnings().Count - warnings0)
    + (newWarnings.Any() ? " :: " + string.Join(" | ", newWarnings) : ""));
sb.AppendLine("column ids: " + string.Join(",", ids.Select(x => x.Value)));
return sb.ToString();
