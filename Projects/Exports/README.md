# Projects/Exports - Automation Scripts

This directory contains automation scripts for batch processing and error correction in Revit projects.

## 📋 Overview

These scripts are designed for automated execution, particularly useful for:
- Batch error correction
- Model cleanup and validation
- Automated fixes for common Revit warnings/errors

## 🔧 Scripts Inventory

### Master Script

#### `EJECUTAR_TODOS_LOS_SCRIPTS.py`
Master script that executes all error correction scripts in sequence.

**Features:**
- Automatic execution of multiple scripts
- Error handling and reporting
- Confirmation dialog before execution
- Compatible with Python 2 and 3

**Usage:**
```python
# Ejecuta desde pyRevit o directamente desde Python
python EJECUTAR_TODOS_LOS_SCRIPTS.py
```

**Executes in order:**
1. `fix_revit_errors.py`
2. `fix_stair_errors.py`
3. `fix_remaining_errors.py`

---

### Error Correction Scripts

#### `fix_revit_errors.py` (~10,000 bytes)
General error correction for common Revit issues.

**Fixes:**
- Generic Revit warnings
- Element errors
- Model validation issues

#### `fix_stair_errors.py` (~6,400 bytes)
Specific corrections for stair-related errors.

**Fixes:**
- Stair path inconsistencies
- Railing errors
- Landing issues

#### `fix_remaining_errors.py` (~5,900 bytes)
Handles remaining errors not covered by other scripts.

**Fixes:**
- Edge cases
- Specific project errors
- Custom validations

#### `fix_spot_elevations_toposolid.py` (~5,600 bytes)
Corrects spot elevation issues related to toposolids.

**Fixes:**
- Spot elevation placement
- Toposolid references
- Elevation inconsistencies

---

### Geometry Processing

#### `EditToposolidContourCurves.py` (~6,800 bytes)
Edits contour curves of toposolid elements.

**Features:**
- Contour curve modification
- Toposolid geometry editing
- Automated curve adjustments

**Related Files:**
- `EditToposolidContourCurves.dyn` - Dynamo version
- `EditToposolidContourCurves_Complete.py` - Complete version
- `EditToposolidContourCurves_Simplified.dyn` - Simplified Dynamo version

**Documentation:** See `README_EditToposolidCurves.md`

#### `activate_curved_edge_condition.py` (~10,600 bytes)
Activates curved edge conditions on elements.

**Features:**
- Curved edge detection
- Condition activation
- Edge modification

#### `convert_shaft_to_shaft_opening.py` (~11,000 bytes)
Converts shaft elements to shaft openings.

**Features:**
- Shaft element detection
- Automatic conversion
- Opening creation

---

### Dimensioning

#### `dimensionar_muros_planta.py` (~39,100 bytes) ⚠️ LARGE FILE
Automatic wall dimensioning in plan views.

**Features:**
- Similar to `DimensionWalls.pushbutton` in NOSA.tab
- Batch processing mode
- Automation-friendly

**Documentation:** See `README_dimensionar_muros.md`

**Note:** This appears to be a standalone version of the DimensionWalls tool for batch automation.

---

### View Management

#### `show_levels_in_sections.py` (~2,400 bytes)
Shows level annotations in section views.

**Features:**
- Automatic level visibility
- Section view processing
- Level annotation placement

---

## 📚 Documentation Files

| File | Description |
|------|-------------|
| `INSTRUCCIONES.md` | General instructions for using automation scripts |
| `MEJORAS_IMPLEMENTADAS.md` | Log of improvements made to scripts |
| `README_CORRECCION_ERRORES.md` | Error correction documentation |
| `README_EditToposolidCurves.md` | Toposolid editing documentation |
| `README_dimensionar_muros.md` | Wall dimensioning documentation |

---

## 🚀 Usage Patterns

### Pattern 1: Master Script (Recommended)
```python
# Run all correction scripts at once
python EJECUTAR_TODOS_LOS_SCRIPTS.py
```

### Pattern 2: Individual Scripts
```python
# Run specific script for targeted fixes
python fix_stair_errors.py
```

### Pattern 3: Batch Processing
```python
# Process multiple projects
for project in projects:
    open_project(project)
    run_script("fix_revit_errors.py")
    save_and_close()
```

---

## ⚠️ Important Notes

### Before Running
1. **Backup your model** - Always create a backup before running automated scripts
2. **Close worksheets** - Close any open worksheets to avoid conflicts
3. **Check permissions** - Ensure you have write permissions

### After Running
1. **Review errors** - Check Revit warnings/errors dialog
2. **Validate changes** - Visual inspection of affected elements
3. **Save incrementally** - Save with a new version number

### Compatibility
- Compatible with Revit 2024-2026
- Python 2.7 and 3.x compatible
- Requires pyRevit or standalone Python with Revit API

---

## 🔄 Integration with NOSA Extension

Some scripts in this directory have interactive equivalents in the NOSA.tab:

| Automation Script | Interactive Tool |
|-------------------|------------------|
| `dimensionar_muros_planta.py` | `DimensionWalls.pushbutton` |
| - | `TagAll.pushbutton` |
| - | `PileCoordinates.pushbutton` |

**Use automation scripts for:**
- Batch processing multiple projects
- Scheduled/automated workflows
-Non-interactive execution

**Use interactive tools for:**
- Single project work
- User decisions required
- Preview before execution

---

## 📊 Recommended Workflow

### 1. Model Cleanup Workflow
```
1. Open project
2. Run EJECUTAR_TODOS_LOS_SCRIPTS.py
3. Review Revit warnings
4. Run specific scripts if needed
5. Validate and save
```

### 2. Pre-Export Workflow
```
1. Run fix_revit_errors.py
2. Run fix_spot_elevations_toposolid.py (if using toposolids)
3. Run show_levels_in_sections.py
4. Export with Export Sheets Pro
```

### 3. Regular Maintenance
```
Weekly: Run EJECUTAR_TODOS_LOS_SCRIPTS.py
Monthly: Review and update automation scripts
Quarterly: Backup and version control
```

---

## 🛠️ Potential Improvements

### Future Enhancements
- [ ] Integrate with `nosa_utils` library for consistency
- [ ] Add logging to all scripts
- [ ] Create progress reporting
- [ ] Unify error handling
- [ ] Add configuration files for batch processing
- [ ] Create test suite for validation

### Code Quality
- [ ] Refactor large files (dimensionar_muros_planta.py is 39KB)
- [ ] Add docstrings to all functions
- [ ] Standardize naming conventions
- [ ] Remove code duplication

---

## 📖 Additional Resources

- See individual README files for detailed documentation
- Check MEJORAS_IMPLEMENTADAS.md for improvement history
- Refer to INSTRUCCIONES.md for step-by-step guides

---

**Last Updated:** January 2026  
**Maintained by:** Antonio Viñas
