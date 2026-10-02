# -*- coding: utf-8 -*-
"""
UI Helper Utilities
Provides common user interface functions and helpers.
"""

from pyrevit import forms, script
import os
import json
from nosa_utils.telemetry import log_swallowed
_LOG = u'nosa_utils.ui_helpers'

# =============================================================================
# PROGRESS REPORTING
# =============================================================================

def show_progress(current, total, message="Processing..."):
    """
    Display progress in output window.
    
    Args:
        current (int): Current item number
        total (int): Total number of items
        message (str): Progress message
        
    Example:
        >>> for i, item in enumerate(items, 1):
        >>>     show_progress(i, len(items), "Processing items")
        >>>     process(item)
    """
    output = script.get_output()
    percentage = (float(current) / total) * 100 if total > 0 else 0
    output.update_progress(current, total)
    if current % 10 == 0 or current == total:
        output.print_md("**Progress:** {}/{} ({:.1f}%) - {}".format(
            current, total, percentage, message
        ))


# =============================================================================
# USER INPUT HELPERS
# =============================================================================

def ask_for_number(prompt, default=None, min_value=None, max_value=None, title="Input Required"):
    """
    Ask user for a numeric input with validation.
    
    Args:
        prompt (str): Prompt message
        default: Default value
        min_value: Minimum acceptable value
        max_value: Maximum acceptable value
        title (str): Dialog title
        
    Returns:
        float: User input, or None if cancelled
        
    Example:
        >>> spacing = ask_for_number("Enter spacing (mm):", default=1500, min_value=300)
        >>> if spacing:
        >>>     print("User entered:", spacing)
    """
    default_str = str(default) if default is not None else ""
    value_str = forms.ask_for_string(
        default=default_str,
        prompt=prompt,
        title=title
    )
    
    if value_str is None:
        return None
    
    try:
        value = float(value_str)
        
        if min_value is not None and value < min_value:
            forms.alert(
                "Value must be at least {}. You entered: {}".format(min_value, value),
                title="Invalid Input"
            )
            return None
        
        if max_value is not None and value > max_value:
            forms.alert(
                "Value cannot exceed {}. You entered: {}".format(max_value, value),
                title="Invalid Input"
            )
            return None
        
        return value
    
    except ValueError:
        forms.alert(
            "Invalid number format: '{}'".format(value_str),
            title="Invalid Input"
        )
        return None


def ask_for_choice(options, title="Select an option", default=None, multiselect=False):
    """
    Ask user to select from a list of options.
    
    Args:
        options (list): List of options to choose from
        title (str): Dialog title
        default: Default selection
        multiselect (bool): Allow multiple selections
        
    Returns:
        Selected option(s), or None if cancelled
        
    Example:
        >>> types = ["Type A", "Type B", "Type C"]
        >>> selected = ask_for_choice(types, "Select type")
        >>> if selected:
        >>>     print("User selected:", selected)
    """
    if multiselect:
        return forms.SelectFromList.show(
            options,
            title=title,
            multiselect=True
        )
    else:
        return forms.ask_for_one_item(
            options,
            default=default,
            title=title
        )


def confirm_action(message, title="Confirm"):
    """
    Ask user to confirm an action.
    
    Args:
        message (str): Confirmation message
        title (str): Dialog title
        
    Returns:
        bool: True if confirmed, False otherwise
        
    Example:
        >>> if confirm_action("Delete 50 elements?"):
        >>>     delete_elements()
    """
    return forms.alert(
        message,
        title=title,
        yes=True,
        no=True
    )


# =============================================================================
# CONFIGURATION PERSISTENCE
# =============================================================================

class ConfigHelper:
    """Helper class for saving and loading configuration values."""
    
    def __init__(self, script_name, config_dir=None):
        """
        Initialize configuration helper.
        
        Args:
            script_name (str): Name of the script (used for config file name)
            config_dir (str): Directory for config files (default: script directory)
        """
        self.script_name = script_name
        
        if config_dir is None:
            # Default to script's directory
            try:
                script_dir = os.path.dirname(__file__)
                self.config_dir = os.path.join(script_dir, 'config')
            except Exception:
                # Fallback if __file__ not available
                self.config_dir = os.path.join(
                    os.getenv('APPDATA'),
                    'pyRevit',
                    'NOSA_Configs'
                )
        else:
            self.config_dir = config_dir
        
        # Ensure config directory exists
        if not os.path.exists(self.config_dir):
            try:
                os.makedirs(self.config_dir)
            except Exception:
                log_swallowed(_LOG, u'ConfigHelper.__init__')
        
        self.config_file = os.path.join(
            self.config_dir,
            "{}_config.json".format(script_name)
        )
    
    def save(self, config_dict):
        """
        Save configuration dictionary to file.
        
        Args:
            config_dict (dict): Configuration to save
            
        Returns:
            bool: True if successful
        """
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
            return True
        except Exception:
            return False
    
    def load(self, defaults=None):
        """
        Load configuration from file.
        
        Args:
            defaults (dict): Default values if file doesn't exist
            
        Returns:
            dict: Loaded configuration or defaults
        """
        if defaults is None:
            defaults = {}
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    return json.load(f)
        except Exception:
            log_swallowed(_LOG, u'ConfigHelper.load')
        
        return defaults
    
    def get(self, key, default=None):
        """Get a single configuration value."""
        config = self.load()
        return config.get(key, default)
    
    def set(self, key, value):
        """Set a single configuration value."""
        config = self.load()
        config[key] = value
        return self.save(config)


# =============================================================================
# RESULT DISPLAY
# =============================================================================

def display_results(title, results_dict, show_zeros=False):
    """
    Display results in a formatted way.
    
    Args:
        title (str): Results title
        results_dict (dict): Dictionary of result key-value pairs
        show_zeros (bool): Whether to show items with value 0
        
    Example:
        >>> display_results("Operation Complete", {
        >>>     "Success": 45,
        >>>     "Failed": 2,
        >>>     "Skipped": 0
        >>> })
    """
    output = script.get_output()
    output.print_md("## {}".format(title))
    output.print_md("")
    
    for key, value in results_dict.items():
        if not show_zeros and value == 0:
            continue
        output.print_md("- **{}:** {}".format(key, value))


def display_summary_table(title, headers, rows):
    """
    Display a markdown table.
    
    Args:
        title (str): Table title
        headers (list): List of header strings
        rows (list): List of row lists
        
    Example:
        >>> display_summary_table("Element Types", 
        >>>     ["Type", "Count"],
        >>>     [["Wall", 45], ["Door", 12], ["Window", 18]]
        >>> )
    """
    output = script.get_output()
    output.print_md("## {}".format(title))
    output.print_md("")
    
    # Header
    header_line = "| {} |".format(" | ".join(str(h) for h in headers))
    separator = "|{}|".format("|".join([" --- "] * len(headers)))
    
    output.print_md(header_line)
    output.print_md(separator)
    
    # Rows
    for row in rows:
        row_line = "| {} |".format(" | ".join(str(cell) for cell in row))
        output.print_md(row_line)
