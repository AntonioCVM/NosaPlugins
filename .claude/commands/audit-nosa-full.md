---
description: Three-axis audit of every active NOSA plugin (code · XAML appearance · usefulness)
---

Run the three-axis audit (MASTER_ROADMAP T6.1) and report it.

1. Run `python tools/audit_3axes.py --usage "<main checkout>/NOSA_Configs/_usage.json"`
   (the usage file lives in the main checkout, not in a worktree). It rewrites
   `docs/AUDIT_3AXES.md`: one row per active `.pushbutton` with launches, lines of code, tests,
   nosa_lint findings (critical/high/medium/low), NOSA colour resources, Century Gothic,
   dark-mode toggle, loading overlay and icon (96×96 + `icon.svg`), plus a findings-by-rule table.
2. Summarise for the user, in Spanish:
   - plugins with critical/high lint findings (fix first),
   - the most used plugins without tests,
   - icons off the 96×96 + `icon.svg` standard (T6.4),
   - rarely used, large plugins (usage vs LOC) as candidates to simplify or retire — a
     product decision for the user, never removed without asking.
3. Do not change code in this command; propose the follow-up tasks instead.
