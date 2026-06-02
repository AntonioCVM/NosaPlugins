# DiRoots-style tools — human smoke checklist

Run in a throwaway sandbox project linked to typical structural content.

## Data › Bulk Parameter Editor (instances)

1. Pick category (e.g. Structural Framing) → **SCAN** without filters → grid fills.
2. Enable **Restrict to Revit selection** → select subset → SCAN → counts drop.
3. Filter parameter list via **substring** filter + scope (**Built-in only** vs **Shared only**).
4. Optional **Secondary (read-only)** column shows Aux values.
5. Edit **New** cells → verify **Dry-run preview** lists correct parameters → APPLY → counts OK.
6. Enter measurable length-like value matching UI units → APPLY → verify model updates.
7. **Save preset**, reload preset from combo, SCAN auto-runs.

## Structures › Elements › Structural Types

1. SCAN types for framing/columns → types appear (not instances).
2. Selection filter: multi-select framing instances → SCAN with **limit to selection**.
3. Duplicate one row → new type id alert → SCAN shows duplicate.
4. Dry-run → APPLY CSV export incl. optional Aux column.

## Data › DiRoots Hub

Launch hub → **Instances** opens Bulk window; relaunch ribbon → hub → **Types** opens Structural Types.

## Log file

Failures append to `%APPDATA%\pyRevit\Extensions\NOSA.extension\NOSA_Logs\diroots_apply.log`.

## Scope limits

Collectors operate on the **active document** only — linked models are out of scope by design.
