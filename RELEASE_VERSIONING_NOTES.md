# NOSA Extension - Release Versioning Notes

Date: 2026-04-17

## Recommended Release Tag

- Suggested extension tag: `v2.2.0`

Rationale:
- New command added (`HalftoneSelection`) -> feature increment.
- Significant behavior improvements in existing tools (Print persistence/range selection, ground beams support).
- No breaking changes to command entrypoints -> minor version bump is appropriate.

## Proposed Tool Version Matrix

- `Export Sheets Pro` -> keep `4.2` (already user-facing and stable in command metadata).
- `Align Element to Column` -> `3.1` (already updated).
- `Waffle Slab` -> `2.1` (already updated).
- `Halftone Selection` -> `1.1` (already updated).

Optional next cleanup release (`v2.2.1`):
- Unify metadata/docstring versions across all scripts for strict consistency.
- Final language harmonization in remaining legacy commands.

## Release Notes (User-Facing Draft)

### Highlights

- New: `Halftone Selection` command in `Views` panel.
- Better print workflows:
  - remembers settings between sessions
  - supports range/mass selection workflows
- Structural alignment enhanced:
  - supports ground beams in addition to beams and pilecaps
- Visual consistency improvements:
  - `Century Gothic` typography in main WPF tools
  - shared dark/light theme behavior

### Reliability Improvements

- Safer error handling in key structural commands.
- Relative library imports for better portability across user profiles/machines.

## Release Packaging Checklist

- [ ] Verify no temporary debug files are included.
- [ ] Validate icon rendering for light/dark ribbon contexts.
- [ ] Run manual QA from `RELEASE_READY_QA_CHECKLIST.md`.
- [ ] Update internal change log with final commit hash.
- [ ] Distribute to pilot users before full rollout.
