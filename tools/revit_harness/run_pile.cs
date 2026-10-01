// Launcher for pile_harness.py — paste into rvt-mcp revit_send_code_to_revit.
// Set EXT_ROOT to the checkout/worktree to test. Rolls back all model changes.
var asm = AppDomain.CurrentDomain.GetAssemblies().First(a => a.GetName().Name == "pyRevitLoader");
var t = asm.GetType("PyRevitLoader.ScriptExecutor");
dynamic exec = t.GetConstructors().First().Invoke(null);
dynamic engine = t.GetMethod("CreateEngine").Invoke(exec, null);
t.GetMethod("AddEmbeddedLib").Invoke(exec, new object[] { engine });
string appdata = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
string ext = appdata + @"\pyRevit\Extensions\NOSA.extension";
dynamic scope = engine.CreateScope();
scope.SetVariable("doc", doc);
scope.SetVariable("EXT_ROOT", ext);
scope.SetVariable("PYREVIT", appdata + @"\pyRevit-Master");
engine.ExecuteFile(ext + @"\tools\revit_harness\pile_harness.py", scope);
return (string)scope.GetVariable("RESULT");
