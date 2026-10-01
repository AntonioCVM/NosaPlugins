# RebarAutomate — User Guide

NOSA pyRevit extension · Structures panel → Quantities → **RebarAutomate**
Revit 2024 · 2025 · 2026 · 2027 · Standard: **BS 8666:2020 / BS EN 1992-1-1 (UK NA)**

RebarAutomate models the reinforcement of footings, slabs, columns, beams and walls,
marks every bar to BS 8666, tags it and feeds the bar bending schedule (BBS) and the
BVBS file for the bending machine.

---

## 1. Before you start

**Use the NOSA template (v30 or later).** It carries everything the tool relies on:

| Item | Why it matters |
|---|---|
| `NOSA Rebar Tag` 1.0.0 (Full label / Mark only × Arrow / Dot) | Bar labels such as `12H16-03-200 B1` |
| Multi-Rebar Annotation types *Zone label - Dots / No dots / Mark only* | Zone labels |
| Rebar shapes 00–98 | BS 8666 shape codes; each shape only carries its own dimensions, so unused BBS columns stay blank |
| `BBS` schedule | BS 8666 columns, sorted by Member (Partition) and Bar mark |
| Reinforcement rounding: bar length **Up 25 mm**, segments **Down 5 mm** | Cut lengths and dimensions as BS 8666 expects |
| Project parameters *Number of Members*, *Rebar revision* | BBS columns *No. of mbrs* and *Rev. letter* |

The NOSA shared parameters (`NOSA_Rebar_*`) are bound automatically on the first run.

**Host materials.** Concrete strength is read from the host material — a structural asset,
or a class in the name such as `Concrete - RC32/40`. If neither exists, the project default
fck is used (see §2).

**Covers.** Each host's native *Rebar Cover* parameters (top, bottom, other faces) are used.

---

## 2. Project settings (top of the window)

| Field | Meaning |
|---|---|
| **Standard** | Defaults to **BS-8666-2020**. Change it only for non-UK work |
| **Partition** | The schedule / drawing the bars belong to (e.g. `Slab L1`). Bar marks restart at 01 in each partition and the BBS *Member* column shows it |
| **Lap rules** | *EC2 — BS EN 1992-1-1 (UK NA)* (default) or *BS 8110 — legacy multiples* |
| **Default fck (MPa)** | Used when the host material does not say its strength |

Press **Save Project Settings** to keep them with this model.

---

## 3. Generating reinforcement

Select the host elements in the model, open the matching tab, set the values and press
**GENERATE REINFORCEMENT**. Every run is one *batch*: it can be selected or deleted as a
whole from the *Detailing & Tools* tab.

Fields showing **Auto** compute the lap or anchorage from the lap rules. Type a number to
override it (never below max(15φ, 300 mm)).

### 3.1 Footings & Slabs

- **Bottom mat / Top mat** — X bars are the outer layer (**B1**, **T1**), Y bars the inner
  layer (**B2**, **T2**). The layer code is written to *Comments* and shown on the label.
- **Max stock length** — longer bars are split with laps. Alternate rows are **staggered**
  by 1.3 l0, so at most half the bars lap at one section (EC2 8.7.2: α6 = 1.4).
- **Perimeter closure U-bars** — one U-bar beside each mat bar on every edge (straight or
  skewed), legs = full lap with the mat bars and at least 2h (EC2 9.3.1.4). Their back
  sits at cover + bar radius, so all edges get identical legs. Skewed edges are grouped in a
  single element per edge and still schedule as shape 21.
- **45° diagonal bars** at the corners of openings larger than 200 × 200 mm (slabs only).
- **Dowels** — one per column vertical under each column on the footing.
- **Detail sections** — two centred sections per footing.

### 3.2 Columns

- Links with **densified zones** at the nodes (including intermediate floors).
- Every floor crossing gets a lap. Bars **≥ H20 crank one diameter at 1:6** (BS 8666
  shape 26), finishing just below the slab top; **≤ H16 lap straight**, side by side. A
  smaller column above always cranks by the reduction. The lap is measured above the kicker.
- At the top of the last column, bars end in an **L foot inside the slab**, below the slab's
  real top mat, turned into the slab at edges and corners.
- Optional starters into the foundation below.

### 3.3 Beams

Straight rectangular beams: top and bottom bars, stirrups with dense end zones
(auto length = 2 × beam depth), stock-length splits with laps.

### 3.4 Walls

- Mesh on one or both faces. Faces are coded **NF** (towards the slab) and **FF**
  (outside the building); the code goes to *Comments* and the label.
- **Coronation (top) U-bars** — one beside each vertical bar, legs = full lap with the
  verticals, back at cover + radius under the wall head. The top horizontal bar is kept
  under the U-bar back.
- **End U-bars** — one beside each horizontal bar at both free ends, legs = full lap.
- Through-wall ties, straight or L starters into the foundation.

### 3.5 What every element gets

- **25 mm detailing** — laps and anchorages are rounded **up** to 25 mm; straight bars are
  trimmed equally at both ends to a whole 25 mm, so the BBS shows A = length.
- **Shape codes** — bars are matched to the template shapes (00, 11, 21, 26, 51 …).
- **Bar marks (BS 8666)** — identical bars (diameter, shape, dimensions, length) share one
  mark: 01, 02 … within the partition, continuing from marks already used. A varying set
  keeps one mark, listed as 05A, 05B … in the schedule (I, O and Q skipped).
- **Number of Members** = 1 when empty (never over a value you typed).

---

## 4. Labels and annotations

**Auto Tag Selection** (or tagging during generation, in a plan or locked 3D view):

| View | Tag type |
|---|---|
| Plans and elevations | **Full label** — e.g. `12H16-03-200 B1` |
| Sections and details | **Mark only** — e.g. `03` |

The leader end (Arrow / Dot) follows the type chosen in the drop-down; Dot by default.
A multiplier such as `2x12H16-…` appears only if you type `2x` in the bar's
`NOSA_Rebar_Label_Multiplier` parameter (empty = nothing shown).

**Auto MRA…** places a Multi-Rebar Annotation (zone label) on the selected set.
**Auto Detail Sections (X + Y)…** cuts two sections through the selected hosts.

> Tagging is skipped in an *unlocked* 3D view — lock it or use a plan view.

---

## 5. Schedules and fabrication

**Revit BBS schedule** (template): Member · Bar mark · Type and size · No. of mbrs ·
No. of bars in each · Total no. · Length of each bar · Shape code · A–E · r · Rev. letter ·
Weight (kg). Lengths and dimensions use the reinforcement rounding; unused dimensions are
blank.

**Generate Schedule…** exports the same BBS as **CSV** (opens in Excel), with varying sets
split into 05A, 05B … rows.

**Export BVBS (.abs)…** writes the BF2D file for the bending machine (BVBS Guideline 3.1),
asking for the schedule number. Circular links and custom shapes go without bending
geometry and are bent from the schedule.

**Renumber Partition** renumbers every bar of the current partition from 01.

---

## 6. Batch tools (Detailing & Tools tab)

| Button | Does |
|---|---|
| Refresh | Lists the batches in the model |
| Select in Model | Selects all bars of a batch |
| Delete Batch | Deletes a batch (finalised bars are kept) |
| Load NOSA Families | Loads or updates the packaged `NOSA Rebar Tag`; the card warns when it is missing or out of date |

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| *"Rebar Shape definitions will not include hooks or end treatments…"* when pressing Rebar | Informative only (template setting). Press OK |
| No tags created | Active view is an unlocked 3D view, or the tag family is not loaded |
| BBS shows *mm* in every cell | The *Reinforcement Length* project unit has a symbol — set it to none |
| Laps look short / long | Check *Lap rules*, the host material class and *Default fck* |
| A bar mark repeats for different bars | Run **Renumber Partition** |
| Shape 00 instead of 21 on old bars | Regenerate them: bars made before the fix keep their old shape |

---

## 8. Known limitations (1.0)

- Beams and walls must be straight; curved hosts are not supported.
- Wall mesh laps are not staggered (100 % lapped, α6 = 1.5 — conservative).
- Template shapes 13, 22, 33 (180° bends) and 67, 75, 77 (arcs) still show 0 in unused
  BBS columns.
- The BVBS file has not yet been read by a fabricator's machine.
- Lap / Split / Extend / Copy to Similar Hosts / Delete Host Rebars / Show as Solids are
  planned for a later release and hidden in 1.0.
