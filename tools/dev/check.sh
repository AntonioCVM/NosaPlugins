#!/bin/bash
# Run both suites from this worktree, then copy the files it changed into the live extension (main checkout).
# Usage: bash tools/dev/check.sh   (run from anywhere)
PY="${NOSA_PY:-/c/Users/AntonioCViñas/AppData/Local/Programs/Python/Python312/python.exe}"
W="$(cd "$(dirname "$0")/../.." && pwd)"
M="$(cd "$W/../../.." && pwd)"
S="${TEMP:-/tmp}/nosa_tools"; mkdir -p "$S"
cd "$W/tests" && echo "root unittest: $("$PY" -m unittest discover -p 'test_*.py' 2>&1 | tail -1)"
cd "$W" && "$PY" "$W/tools/dev/runtests.py" > "$S/rt_root.txt" 2>&1; echo "root functions: $(tail -1 "$S/rt_root.txt")"; grep "^FAIL\|IMPORT FAIL" "$S/rt_root.txt"
cd "$W/NOSA.tab/Reinforcement.panel/RebarAutomate.pushbutton" && "$PY" "$W/tools/dev/runtests.py" > "$S/rt.txt" 2>&1; echo "plugin: $(tail -1 "$S/rt.txt")"; grep "^FAIL\|IMPORT FAIL" "$S/rt.txt"
cd "$W" && for f in $(git status --short | awk '{print $2}' | grep -E "^(NOSA.tab|lib)/"); do [ -f "$W/$f" ] && cp "$W/$f" "$M/$f"; done; git status --short | grep -v "^??"
