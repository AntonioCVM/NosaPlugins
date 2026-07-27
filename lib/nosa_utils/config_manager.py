# -*- coding: utf-8 -*-
"""
Configuration Manager
Centralized configuration management for NOSA scripts.
"""

import os
import json

# =============================================================================
# CONFIGURATION MANAGER
# =============================================================================

class ConfigManager:
    """
    Centralized configuration manager for script settings.
    Handles loading, saving, and validation of configuration files.
    """
    
    DEFAULT_CONFIG_DIR = os.path.join(
        os.getenv('APPDATA', ''),
        'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs'
    )
    
    def __init__(self, config_name, config_dir=None):
        """
        Initialize configuration manager.
        
        Args:
            config_name (str): Name of configuration file (without extension)
            config_dir (str): Directory for config files (default: APPDATA/pyRevit/NOSA_Configs)
            
        Example:
            >>> config = ConfigManager("pile_spacing")
            >>> config.set("last_spacing_mm", 1500)
            >>> spacing = config.get("last_spacing_mm", 1000)
        """
        self.config_name = config_name
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_file = os.path.join(
            self.config_dir,
            "{}.json".format(config_name)
        )
        self._data = None
        
        # Ensure config directory exists
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Create config directory if it doesn't exist."""
        if not os.path.exists(self.config_dir):
            try:
                os.makedirs(self.config_dir)
            except Exception:
                pass
    
    def load(self):
        """Load configuration from file. Returns dict."""
        if self._data is not None:
            return self._data

        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self._data = json.load(f)
                    return self._data
        except Exception as ex:
            try:
                from nosa_utils.telemetry import log_error
                log_error('ConfigManager', str(ex))
            except Exception:
                pass

        self._data = {}
        return self._data

    def load_with_defaults(self, defaults):
        """
        Load config and fill any missing keys from defaults.

        Saved values take priority; new keys in defaults are added on first save.
        """
        data = self.load()
        merged = dict(defaults)
        merged.update(data)
        return merged

    def save(self):
        """Save current configuration to file. Returns True on success."""
        if self._data is None:
            return False

        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._data, f, indent=2)
            return True
        except Exception as ex:
            try:
                from nosa_utils.telemetry import log_error
                log_error('ConfigManager', str(ex))
            except Exception:
                pass
            return False
    
    def get(self, key, default=None):
        """
        Get a configuration value.
        
        Args:
            key (str): Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        data = self.load()
        return data.get(key, default)
    
    def set(self, key, value):
        """
        Set a configuration value.
        
        Args:
            key (str): Configuration key
            value: Value to set
            
        Returns:
            bool: True if successfully saved
        """
        data = self.load()
        data[key] = value
        return self.save()
    
    def update(self, updates_dict):
        """
        Update multiple configuration values at once.
        
        Args:
            updates_dict (dict): Dictionary of key-value pairs to update
            
        Returns:
            bool: True if successfully saved
        """
        data = self.load()
        data.update(updates_dict)
        return self.save()
    
    def delete(self, key):
        """
        Delete a configuration value.
        
        Args:
            key (str): Configuration key to delete
            
        Returns:
            bool: True if successfully saved
        """
        data = self.load()
        if key in data:
            del data[key]
            return self.save()
        return False
    
    def clear(self):
        """
        Clear all configuration values.
        
        Returns:
            bool: True if successfully saved
        """
        self._data = {}
        return self.save()
    
    def exists(self):
        """
        Check if configuration file exists.
        
        Returns:
            bool: True if file exists
        """
        return os.path.exists(self.config_file)
    
    def get_all(self):
        """
        Get all configuration values.
        
        Returns:
            dict: All configuration data
        """
        return dict(self.load())


# =============================================================================
# SCHEMA VALIDATION
# =============================================================================

class ConfigSchema:
    """
    Configuration schema validator.
    Ensures configuration values meet expected types and constraints.
    """
    
    def __init__(self, schema_dict):
        """
        Initialize with schema definition.
        
        Args:
            schema_dict (dict): Schema definition with keys and expected types/constraints
                Example: {
                    "spacing_mm": {"type": float, "min": 100, "max": 10000},
                    "use_groups": {"type": bool},
                    "prefix": {"type": str, "max_length": 10}
                }
        """
        self.schema = schema_dict
    
    def validate(self, config_dict):
        """
        Validate configuration against schema.
        
        Args:
            config_dict (dict): Configuration to validate
            
        Returns:
            tuple: (is_valid: bool, errors: list of error messages)
        """
        errors = []
        
        for key, constraints in self.schema.items():
            if key not in config_dict:
                continue  # Optional fields
            
            value = config_dict[key]
            expected_type = constraints.get("type")
            
            # Type check
            if expected_type and not isinstance(value, expected_type):
                errors.append("{}: expected {}, got {}".format(
                    key,
                    expected_type.__name__,
                    type(value).__name__
                ))
                continue
            
            # Numeric constraints
            if expected_type in (int, float):
                min_val = constraints.get("min")
                max_val = constraints.get("max")
                
                if min_val is not None and value < min_val:
                    errors.append("{}: value {} below minimum {}".format(
                        key, value, min_val
                    ))
                
                if max_val is not None and value > max_val:
                    errors.append("{}: value {} above maximum {}".format(
                        key, value, max_val
                    ))
            
            # String constraints
            if expected_type == str:
                max_length = constraints.get("max_length")
                if max_length and len(value) > max_length:
                    errors.append("{}: length {} exceeds maximum {}".format(
                        key, len(value), max_length
                    ))
        
        return (len(errors) == 0, errors)
