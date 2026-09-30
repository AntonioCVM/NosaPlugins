// Re-arm a test model from scratch with the current RebarAutomate (rvt-mcp
// revit_send_code_to_revit body). Deletes ALL rebar, then runs footings/floors,
// columns, walls and beams through ra_harness.py. Edit the ids per model.
// Test models only: guarded by the document title.
var ids = new Dictionary<string, long[]> {
    { "footings_floors", new long[] { /* footings, mat slab, strip footing, floor */ } },
    { "columns", new long[] { } },
    { "walls", new long[] { } },
    { "beams", new long[] { } } };
var controls = new Dictionary<string, string> {
    { "footings_floors", "{\"ChkIncludeDowels\": false, \"ChkIncludeTopMat\": true, \"ChkIncludePerimeterUBars\": true}" },
    { "columns", "{\"ChkColFoundationStarters\": true}" },
    { "walls", "{\"ChkWallFoundationStarters\": true, \"ChkWallStarters\": false}" },
    { "beams", "{}" } };
var allowed = new[] { "Rebar test", "Project1", "Project2" };
if (!allowed.Contains(doc.Title)) return "ABORT " + doc.Title;
var rebar = new FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.Structure.Rebar)).ToElementIds();
using (var tr = new Transaction(doc, "NOSA test - reset rebar")) { tr.Start(); doc.Delete(rebar); tr.Commit(); }
var asm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "pyRevitLoader");
var t = asm.GetType("PyRevitLoader.ScriptExecutor");
dynamic exec = t.GetConstructors().First().Invoke(null);
string ext = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit\Extensions\NOSA.extension";
var sb = new System.Text.StringBuilder(doc.Application.VersionNumber + " " + doc.Title + ": deleted " + rebar.Count + "\n");
foreach (var mode in new[] { "footings_floors", "columns", "walls", "beams" }) {
    if (ids[mode].Length == 0) continue;
    dynamic engine = t.GetMethod("CreateEngine").Invoke(exec, null);
    t.GetMethod("AddEmbeddedLib").Invoke(exec, new object[] { engine });
    dynamic scope = engine.CreateScope();
    scope.SetVariable("doc", doc); scope.SetVariable("MODE", mode); scope.SetVariable("IDS", ids[mode]);
    scope.SetVariable("CONTROLS", controls[mode]); scope.SetVariable("OVERRIDES", "{}");
    scope.SetVariable("EXT_ROOT", ext);
    scope.SetVariable("PYREVIT", Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit-Master");
    engine.ExecuteFile(ext + @"\tools\revit_harness\ra_harness.py", scope);
    var res = (string)scope.GetVariable("RESULT");
    foreach (var l in res.Split('\n'))
        if (l.Contains("created") || l.Contains("EXCEPTION") || l.Contains("Shapes:") || l.Contains("failed")) sb.AppendLine(mode + ": " + l.Trim());
}
return sb.ToString();
