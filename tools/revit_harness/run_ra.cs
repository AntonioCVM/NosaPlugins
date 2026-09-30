// Launcher for ra_harness.py — paste into rvt-mcp revit_send_code_to_revit
// (body of a method with `doc` in scope). Uses pyRevit's own loader so the
// embedded IronPython 2.7.12 stdlib is available. Edit MODE / IDS / CONTROLS.
var asm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "pyRevitLoader");
var t = asm.GetType("PyRevitLoader.ScriptExecutor");
dynamic exec = t.GetConstructors().First().Invoke(null);
dynamic engine = t.GetMethod("CreateEngine").Invoke(exec, null);
t.GetMethod("AddEmbeddedLib").Invoke(exec, new object[] { engine });
string ext = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit\Extensions\NOSA.extension";
dynamic scope = engine.CreateScope();
scope.SetVariable("doc", doc);
scope.SetVariable("MODE", "footings_floors");          // columns | beams | walls
scope.SetVariable("IDS", new long[] { 1317360 });
scope.SetVariable("CONTROLS", "{\"ChkIncludeDowels\": true}");
scope.SetVariable("OVERRIDES", "{}");
scope.SetVariable("EXT_ROOT", ext);
scope.SetVariable("PYREVIT", Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData) + @"\pyRevit-Master");
engine.ExecuteFile(ext + @"\tools\revit_harness\ra_harness.py", scope);
return (string)scope.GetVariable("RESULT");
