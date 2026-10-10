// T8.56 benchmark — paste into rvt-mcp revit_send_code_to_revit (body with `doc` in scope), on the unsaved
// test project only. A 40 x 30 m, 300 mm slab with twelve 800 x 600 openings is reinforced top and bottom
// through RebarAutomate's real path (ra_harness.py), timed, and everything is rolled back.
// Target (MASTER_ROADMAP T8.56): 2000 bars in under 60 s. Measured 2026-10-11, Revit 2024:
//   30 x 20 m, 6 openings:  198 elements, 1601 bars, 19.7 s
//   40 x 30 m, 12 openings: 378 elements, 3177 bars, 44.7 s  (about 0.12 s per element)
// Close Revit's 'Project Not Saved Recently' reminder first: it blocks the run and spoils the time.
if (doc.Application.VersionNumber != "2024") return "WRONG REVIT";
if (doc.Title != "Project1" || doc.PathName != "") return "not the test project: " + doc.Title;
Func<double,double> f = mm => mm / 304.8;
var g = new TransactionGroup(doc, "NOSA perf T8.56"); g.Start();
long floorId = 0;
using (var t = new Transaction(doc, "geometry")) { t.Start();
  double x0 = 200000, y0 = 0;
  var loops = new List<CurveLoop>();
  var outer = new CurveLoop(); var p = new[]{ new XYZ(f(x0),f(y0),0), new XYZ(f(x0+40000),f(y0),0), new XYZ(f(x0+40000),f(y0+30000),0), new XYZ(f(x0),f(y0+30000),0)};
  for (int i=0;i<4;i++) outer.Append(Line.CreateBound(p[i], p[(i+1)%4])); loops.Add(outer);
  for (int k=0;k<12;k++) { double hx = x0 + 3000 + (k%4)*9000, hy = y0 + 4000 + (k/4)*9000;
    var h = new CurveLoop(); var q = new[]{ new XYZ(f(hx),f(hy),0), new XYZ(f(hx+800),f(hy),0), new XYZ(f(hx+800),f(hy+600),0), new XYZ(f(hx),f(hy+600),0)};
    for (int i=0;i<4;i++) h.Append(Line.CreateBound(q[i], q[(i+1)%4])); loops.Add(h); }
  var ft = new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<FloorType>().First(x => x.Name.StartsWith("300mm RC"));
  var fl = Floor.Create(doc, loops, ft.Id, new FilteredElementCollector(doc).OfClass(typeof(Level)).FirstElementId());
  fl.get_Parameter(BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).Set(1);
  floorId = fl.Id.Value; t.Commit(); }
var asm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "pyRevitLoader");
var ty = asm.GetType("PyRevitLoader.ScriptExecutor");
dynamic ex = ty.GetConstructors().First().Invoke(null); dynamic engine = ty.GetMethod("CreateEngine").Invoke(ex, null); ty.GetMethod("AddEmbeddedLib").Invoke(ex, new object[] { engine });
string ext = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit\Extensions\NOSA.extension";
dynamic scope = engine.CreateScope();
scope.SetVariable("doc", doc); scope.SetVariable("MODE", "footings_floors"); scope.SetVariable("IDS", new long[] { floorId });
scope.SetVariable("CONTROLS", "{\"ChkIncludeTopMat\": true, \"ChkFabric\": false, \"ChkFlatSlab\": false, \"ChkAlternateBottom\": false, \"ChkGenerateSections\": false, \"ChkTopOverSupports\": false}");
scope.SetVariable("OVERRIDES", "{}"); scope.SetVariable("EXT_ROOT", ext);
scope.SetVariable("PYREVIT", Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit-Master");
scope.SetVariable("ROLLBACK", true); scope.SetVariable("ASSIMILATE", true);
var sw = System.Diagnostics.Stopwatch.StartNew();
engine.ExecuteFile(ext + @"\tools\revit_harness\ra_harness.py", scope);
sw.Stop();
var rebars = new FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.Structure.Rebar)).Cast<Autodesk.Revit.DB.Structure.Rebar>().Where(r => r.GetHostId().Value == floorId).ToList();
int bars = rebars.Sum(r => r.NumberOfBarPositions);
g.RollBack();
return "time " + sw.Elapsed.TotalSeconds.ToString("F1") + " s, elements " + rebars.Count + ", bars " + bars;
