# -*- coding: utf-8 -*-
__title__ = "Export\nto Excel"
__version__ = "1.0"
__doc__ = """Exports selected schedules to Excel (.xlsx) with formatting.

FEATURES:
✓ Select one or multiple schedules
✓ Export to .xlsx with column widths preserved
✓ Maintains header formatting
✓ Option to export all schedules to single file
✓ Auto-opens file after export
"""
__author__ = "Antonio Viñas"

from pyrevit import revit, DB, forms, script
import os
import sys
import datetime

# Import NOSA utils
extension_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
lib_path = os.path.join(extension_root, "lib")
if lib_path not in sys.path:
    sys.path.append(lib_path)
from nosa_utils import ui_helpers, config_manager
from nosa_utils.revit_helpers import get_id_value

doc = revit.doc
output = script.get_output()

# =============================================================================
# CONFIGURATION
# =============================================================================

config = config_manager.ConfigManager("export_schedule_excel")
DEFAULT_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Documents")

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_schedules():
    """Get all ViewSchedule elements in the project."""
    collector = DB.FilteredElementCollector(doc)\
        .OfClass(DB.ViewSchedule)\
        .WhereElementIsNotElementType()
    
    schedules = []
    for sch in collector:
        # Exclude template schedules and internal schedules
        if not sch.IsTemplate and sch.Name:
            # Exclude revision schedules and internal system schedules
            if not sch.Name.startswith("<") and "Revision" not in sch.Name:
                schedules.append(sch)
    
    return sorted(schedules, key=lambda x: x.Name)


def get_schedule_data(schedule):
    """Extract data from a schedule as a list of lists."""
    table_data = schedule.GetTableData()
    section_data = table_data.GetSectionData(DB.SectionType.Body)
    
    rows = section_data.NumberOfRows
    cols = section_data.NumberOfColumns
    
    data = []
    
    # Get headers first
    header_data = table_data.GetSectionData(DB.SectionType.Header)
    if header_data.NumberOfRows > 0:
        header_row = []
        for col in range(header_data.NumberOfColumns):
            try:
                cell_text = schedule.GetCellText(DB.SectionType.Header, 0, col)
                header_row.append(cell_text)
            except Exception:
                header_row.append("")
        if any(header_row):
            data.append(header_row)
    
    # Get body data
    for row in range(rows):
        row_data = []
        for col in range(cols):
            try:
                cell_text = schedule.GetCellText(DB.SectionType.Body, row, col)
                row_data.append(cell_text)
            except Exception:
                row_data.append("")
        data.append(row_data)
    
    return data


def get_column_widths(schedule):
    """Get column widths from schedule for Excel formatting."""
    table_data = schedule.GetTableData()
    section_data = table_data.GetSectionData(DB.SectionType.Body)
    
    widths = []
    for col in range(section_data.NumberOfColumns):
        try:
            # Get width in feet, convert to approximate Excel column width
            width_ft = section_data.GetColumnWidth(col)
            # Convert feet to approximate character width (1 ft ≈ 15 chars)
            char_width = max(8, int(width_ft * 50))
            widths.append(char_width)
        except Exception:
            widths.append(15)
    
    return widths


def export_to_excel_openpyxl(data, widths, output_path, sheet_name="Schedule"):
    """Export data to Excel using openpyxl."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return False, "openpyxl not available"
    
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]  # Excel limit is 31 chars
    
    # Write data
    for row_idx, row in enumerate(data, 1):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            
            # Style header row
            if row_idx == 1:
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="CCCCCC", 
                                        end_color="CCCCCC", 
                                        fill_type="solid")
                cell.alignment = Alignment(horizontal="center")
            
            # Add borders
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            cell.border = thin_border
    
    # Set column widths
    for col_idx, width in enumerate(widths, 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width
    
    # Freeze header row
    ws.freeze_panes = "A2"
    
    # Save
    wb.save(output_path)
    return True, None


def export_to_csv_fallback(data, output_path):
    """Fallback to CSV if openpyxl not available."""
    import codecs
    
    csv_path = output_path.replace(".xlsx", ".csv")
    
    # Use codecs.open for IronPython 2.7 compatibility
    with codecs.open(csv_path, 'w', encoding='utf-8-sig') as f:
        for row in data:
            # Manual CSV writing for IronPython compatibility
            line_parts = []
            for cell in row:
                cell_str = unicode(cell) if cell is not None else u""
                # Escape quotes and wrap in quotes if needed
                if u',' in cell_str or u'"' in cell_str or u'\n' in cell_str:
                    cell_str = u'"' + cell_str.replace(u'"', u'""') + u'"'
                line_parts.append(cell_str)
            f.write(u','.join(line_parts) + u'\n')
    
    return csv_path


def sanitize_filename(name):
    """Remove invalid characters from filename."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, '_')
    return name


# =============================================================================
# MAIN SCRIPT
# =============================================================================

output.print_md("## 📊 Export Schedule to Excel")
output.print_md("")

# Get all schedules
all_schedules = get_all_schedules()

if not all_schedules:
    forms.alert("No schedules found in the project.", exitscript=True)

# Create selection list
schedule_options = {sch.Name: sch for sch in all_schedules}

# Ask user to select schedules
selected_names = forms.SelectFromList.show(
    sorted(schedule_options.keys()),
    title="Select Schedules to Export",
    multiselect=True,
    button_name="Export"
)

if not selected_names:
    forms.alert("No schedules selected.", exitscript=True)

selected_schedules = [schedule_options[name] for name in selected_names]

output.print_md("**Selected schedules:** {}".format(len(selected_schedules)))
output.print_md("")

# Ask for output directory
last_dir = config.get("last_output_dir", DEFAULT_OUTPUT_DIR)

output_dir = forms.pick_folder(title="Select Output Folder")
if not output_dir:
    forms.alert("No output folder selected.", exitscript=True)

# Save last directory
config.update({"last_output_dir": output_dir})

# Check if openpyxl is available
try:
    from openpyxl import Workbook
    has_openpyxl = True
except ImportError:
    has_openpyxl = False
    output.print_md("> [!WARNING]")
    output.print_md("> openpyxl not installed. Exporting to CSV instead.")
    output.print_md("> To enable Excel export: `pip install openpyxl`")
    output.print_md("")

# Export options
if len(selected_schedules) > 1 and has_openpyxl:
    export_mode = forms.CommandSwitchWindow.show(
        ["Separate Files", "Single File (multiple sheets)"],
        message="Export mode:"
    )
else:
    export_mode = "Separate Files"

# Export
output.print_md("### Exporting...")
output.print_md("")

exported_files = []
failed = []

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

if export_mode == "Single File (multiple sheets)" and has_openpyxl:
    # Export all to one file with multiple sheets
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    
    output_filename = "Schedules_Export_{}.xlsx".format(timestamp)
    output_path = os.path.join(output_dir, output_filename)
    
    wb = Workbook()
    wb.remove(wb.active)  # Remove default sheet
    
    for schedule in selected_schedules:
        try:
            sheet_name = sanitize_filename(schedule.Name)[:31]
            data = get_schedule_data(schedule)
            widths = get_column_widths(schedule)
            
            ws = wb.create_sheet(title=sheet_name)
            
            # Write data with formatting
            for row_idx, row in enumerate(data, 1):
                for col_idx, value in enumerate(row, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)
                    if row_idx == 1:
                        cell.font = Font(bold=True)
                        cell.fill = PatternFill(start_color="CCCCCC", 
                                                end_color="CCCCCC", 
                                                fill_type="solid")
                    thin_border = Border(
                        left=Side(style='thin'),
                        right=Side(style='thin'),
                        top=Side(style='thin'),
                        bottom=Side(style='thin')
                    )
                    cell.border = thin_border
            
            # Set column widths
            for col_idx, width in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(col_idx)].width = width
            
            ws.freeze_panes = "A2"
            
            output.print_md("✓ **{}** - {} rows".format(schedule.Name, len(data)))
        except Exception as e:
            failed.append((schedule.Name, str(e)))
            output.print_md("✗ **{}** - Error: {}".format(schedule.Name, str(e)))
    
    wb.save(output_path)
    exported_files.append(output_path)
    
else:
    # Export each schedule to separate file
    for schedule in selected_schedules:
        try:
            data = get_schedule_data(schedule)
            widths = get_column_widths(schedule)
            
            safe_name = sanitize_filename(schedule.Name)
            
            if has_openpyxl:
                filename = "{}_{}.xlsx".format(safe_name, timestamp)
                output_path = os.path.join(output_dir, filename)
                success, error = export_to_excel_openpyxl(
                    data, widths, output_path, schedule.Name
                )
                if not success:
                    raise Exception(error)
            else:
                filename = "{}_{}.csv".format(safe_name, timestamp)
                output_path = os.path.join(output_dir, filename)
                export_to_csv_fallback(data, output_path)
            
            exported_files.append(output_path)
            output.print_md("✓ **{}** - {} rows → `{}`".format(
                schedule.Name, len(data), filename
            ))
        except Exception as e:
            failed.append((schedule.Name, str(e)))
            output.print_md("✗ **{}** - Error: {}".format(schedule.Name, str(e)))

# Results
output.print_md("")
output.print_md("---")
output.print_md("## ✅ Export Complete")
output.print_md("")

ui_helpers.display_results("Results", {
    "Schedules Exported": len(exported_files),
    "Failed": len(failed),
    "Output Format": "Excel (.xlsx)" if has_openpyxl else "CSV",
    "Output Directory": output_dir
})

# Ask to open files
if exported_files:
    if ui_helpers.confirm_action(
        "Open exported file(s)?",
        title="Open Files"
    ):
        for filepath in exported_files[:3]:  # Limit to first 3
            try:
                os.startfile(filepath)
            except Exception:
                pass

if failed:
    output.print_md("")
    output.print_md("### ⚠️ Failed Exports")
    for name, error in failed:
        output.print_md("- **{}**: {}".format(name, error))

forms.alert(
    "Export Complete!\n\n"
    "✓ Exported: {} schedules\n"
    "✗ Failed: {}\n\n"
    "Output: {}".format(len(exported_files), len(failed), output_dir),
    title="Export Schedule to Excel"
)
