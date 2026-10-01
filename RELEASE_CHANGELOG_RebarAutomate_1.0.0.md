# RebarAutomate 1.0.0 — Release Notes

Released 2026-10-01 after the smoke test of MASTER_ROADMAP T4.5 (Revit 2026, NOSA template v30:
footings, columns, beam, slab with an opening, wall — 74 rebar elements, no Revit warnings).
Standard: BS 8666:2020 / BS EN 1992-1-1 (UK NA). Revit 2024–2027. User guide: `docs/USER_GUIDE.md`.

## Highlights

- **BS 8666 bar marks** — 01, 02 … per partition, shared by identical bars, continued across
  batches; varying sets as 05A, 05B … (no I, O, Q). Written to *Schedule Mark* and *Partition*.
- **Labels to IStructE / BS 8666** — `12H16-03-200 B1`; *Mark only* in sections and details,
  full label in plans and elevations; layer codes B1/B2/T1/T2 and NF/FF filled automatically.
- **Bar bending schedule** — template BBS in BS 8666 columns with the project reinforcement
  rounding; CSV export with the same columns; template rebar shapes carry only their own
  dimensions, so unused columns are blank.
- **BVBS export** (Guideline 3.1) for bending machines.
- **EC2 laps and anchorages** (or BS 8110 legacy), fck from the host material, α6 from the
  share of bars lapped; minimum max(15φ, 300 mm); all rounded up to 25 mm.
- **25 mm detailing** — straight bars trimmed to whole 25 mm (A = cut length in the BBS),
  clear of Revit's end snap to the cover.
- **Exact spacing** — mesh bars at the nominal spacing, centred; labels read `-150`.

## Elements

- **Footings & slabs** — B1/B2/T1/T2 mats; stock-length splits with **staggered laps**
  (α6 1.4); closure U-bars beside every mat bar on every edge, equal legs on skewed edges
  (shape 21); 45° bars at opening corners; dowels; detail sections.
- **Columns** — 135° hooked links (shape 52) densified at every floor; ≥ H20 cranked at 1:6
  (shape 26) below the slab top, ≤ H16 straight; L feet at the top inside the slab, turned in at
  edges/corners; dowels in the footing at the column bar diameter.
- **Beams** — straight rectangular beams; bars run through the supporting columns and end in a
  90° leg (anchorage); 135° hooked links (shape 52) with dense end zones; lapped stock splits;
  warning when a floor cuts the beam.
- **Walls** — NF/FF meshes; end U-bars beside every horizontal with lap legs; coronation
  U-bars at a free head, or verticals running into a slab cast on the head with L feet under
  its top mat; ties; starters into the foundation.

## Fixes since the previous internal builds

- U-bars on skewed slab/footing edges were shape 00 and 5 mm longer than on straight edges.
- FreeForm bar lengths were not rounded like Rebar Sets, splitting identical bars over two marks.
- A new batch restarted marks at 01 in a partition that already had bars.
- Revit 2024 rejected tags on a whole Rebar Set (now tagged through one of its bars).
- Wall mesh spacing could exceed the spacing asked for.
- Documents without settings defaulted to EHE-08 instead of BS 8666.
- BBS CSV export failed on the extra schedule fields; CSV/BVBS mixed partitions sharing a mark.
- The Partition typed in the window was ignored until the settings were saved.
- Beam debug messages were shown to the user.

## Template (00000-NOSA … Revit template v30)

- `NOSA Rebar Tag` 1.0.0 (4 types) and 3 Multi-Rebar Annotation types.
- BBS schedule rebuilt to BS 8666; *Multiplier* / *False Multiplier* retired.
- 30 rebar shapes rebuilt with only their own parameters.
- `NOSA_Rebar_Label_Multiplier` bound to rebar; *Reinforcement Length* shown without unit symbol.

## Known limitations

See `docs/USER_GUIDE.md` §8.
