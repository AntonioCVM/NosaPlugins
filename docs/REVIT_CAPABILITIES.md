# Revit API capabilities and known defects (T8.55)

Written from `data/revit_capabilities.json`, which `tools/revit_harness/capability_probe.py` fills per version: **API** = present in the loaded API (reflection), **live** = a probe in a rolled-back transaction on a test model. The plugin reads the flags with `rebar_engine.api_capabilities()` and the matrix with `nosa_utils.revit_capabilities.supports(version, name)`. Run the probe in each version (Project1 or the template, never a real project) before relying on a feature there.

| Capability | Used for | API member | Revit 2024 | 2025 | 2026 | 2027 |
|---|---|---|---|---|---|---|
| presentation_select | typical bar of a set (SMDSC 6.2.2) | `RebarPresentationMode.Select` | yes / live ok | yes / live ok | yes / live ok | yes / live ok |
| multi_rebar_annotation | indicator lines (MRA) | `DB.MultiReferenceAnnotation` | yes / live ok | yes / live ok | yes / live ok | yes / live ok |
| varying_length | sets following inclined faces | `DistributionType.VaryingLength` | yes / live ok | yes / live ok | yes / live ok | yes / live ok |
| varying_suffix | sub-marks of varying sets | `ReinforcementSettings.RebarVaryingLengthNumberSuffix` | yes | yes | yes | yes |
| free_form | bars with several shapes | `Rebar.CreateFreeForm` | yes | yes | yes | yes |
| couplers | mechanical couplers (T8.52) | `RebarCoupler` | yes / live ok | yes / live ok | yes / live ok | yes / live ok |
| fabric | welded fabric (T8.51) | `FabricArea` | yes / live ok | yes / live ok | yes / live ok | yes / live ok |
| bending_detail | native bending details | `RebarBendingDetail` | yes | yes | yes | yes |
| hook_orientation | hooks up to 2026 | `RebarHookOrientation` | yes | yes | yes | **no** |
| terminations | bar terminations from 2027 | `BarTerminationsData` | no | no | yes | yes |

2025-2027 (2026-10-24): API flags by the probe in a blank project in each version; 'live ok' in 2025-2027 where Create drawings used the feature on the Rebar test models. Couplers and fabric probed live on 2026-10-25 with `SETUP=True` (the probe builds a column, a floor, a plan and a set in a new unsaved project).

## Known defects

| Versions | Area | Defect and work-around |
|---|---|---|
| 2024 | constraints | GetConstraintCandidatesForHandle also offers faces of elements joined to the host; pinning to them moved column links 20 mm in. Filter candidates by their target element. |
| 2024 | creation | Revit trims a beam bar back to the beam's end cover on creation; only the column's far face puts it back. |
| 2024 | sets | A Rebar Set whose distribution normal is not square to the bar plane throws 'An internal error has occurred'. |
| 2024 | free form | Bent FreeForm rebar with arcs opens 'bars in the set cannot be matched to existing rebar shapes' (no preprocessor catches it): never set Bent on arc chains. |
| 2024 | shapes | 'Can't solve Rebar Shape' for a U-bar whose legs are closer than the mandrel (seen again in a 140 mm wall's end U-bars): needs a failures preprocessor with ProceedWithRollBack and SetClearAfterRollback(True). |
| 2024 | tags | A whole Rebar Set cannot be tagged; a tag on one bar (subelement) is drawn only for some bars of the set and has no bounding box. |
| 2024 | tags | NOSA Rebar Tag labels report boxes far wider than their text (about 50 mm on paper): size tags from their text, centred on the head. |
| 2024 | families | About 100 family type loads per external call; later loads throw a managed exception. |
| 2024 | images | ImageType ignores the PNG pHYs chunk and reads 72 dpi: set ImageTypeOptions.Resolution. |
| 2024 | couplers | A coupler between two Rebar Sets is kept only when the sets match bar for bar; otherwise the constraint fails at commit. |
| 2024 | fabric | FabricSheetType size and pitches are read-only properties: set them with SetMajorLayoutAs... / SetMinorLayoutAs...; FabricLocation is TopOrExternal / BottomOrInternal. |
| 2024 | schedules | A schedule takes at most 4 sorting/grouping fields. |
| 2024 | ui | The modal 'Project Not Saved Recently' reminder blocks every API call until it is closed (close it, never save for the user). |
| 2027 | hooks | RebarHookOrientation is replaced by BarTerminationsData (rebar_engine.rebar_from_curves handles both). |
| 2027 | free form | `Rebar.CreateFreeForm(doc, type, host, loops)` with the validation result out is gone: the overload takes a `RebarStyle` and returns a `RebarFreeFormCreationResult` (`.Rebar`, `.Error`). Found by T8.57 (curved beams lost their top and bottom bars); `rebar_engine.create_free_form` handles both. |
| 2026, 2027 | varying sets | `Rebar.DistributionType` is gone: `RebarShapeDrivenAccessor.UseRebarConstraintsToProduceVaryingBars` makes the bars vary (`rebar_engine.set_varying` handles both). |
