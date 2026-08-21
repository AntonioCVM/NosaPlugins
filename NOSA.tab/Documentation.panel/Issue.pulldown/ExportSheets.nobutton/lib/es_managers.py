# -*- coding: utf-8 -*-
import os
import json
import datetime
from Autodesk.Revit import DB
from es_config import Config
from es_utils import Utils
from nosa_utils.logging import Logger

logger = Logger()

class ViewSetManager:
    """Manages saved sheet/view sets."""
    
    @staticmethod
    def get_all_sets():
        sets = []
        try:
            if os.path.exists(Config.VIEWSETS_DIR):
                for filename in os.listdir(Config.VIEWSETS_DIR):
                    if filename.endswith('.json'):
                        sets.append(filename.replace('.json', ''))
        except Exception:
            pass
        return sorted(sets)
    
    @staticmethod
    def save_set(name, sheet_ids):
        try:
            filepath = os.path.join(Config.VIEWSETS_DIR, "{}.json".format(name))
            data = {
                'name': name,
                'sheet_ids': [str(Utils._get_element_id_value(sid)) for sid in sheet_ids],
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False
    
    @staticmethod
    def load_set(name):
        try:
            filepath = os.path.join(Config.VIEWSETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return [DB.ElementId(int(sid)) for sid in data.get('sheet_ids', [])]
        except Exception:
            pass
        return []
    
    @staticmethod
    def delete_set(name):
        try:
            filepath = os.path.join(Config.VIEWSETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def rename_set(old_name, new_name):
        try:
            old_path = os.path.join(Config.VIEWSETS_DIR, "{}.json".format(old_name))
            new_path = os.path.join(Config.VIEWSETS_DIR, "{}.json".format(new_name))
            
            if os.path.exists(old_path):
                with open(old_path, 'r') as f:
                    data = json.load(f)
                
                data['name'] = new_name
                
                with open(new_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                os.remove(old_path)
                return True
        except Exception:
            pass
        return False


class IssuePackageManager:
    """Saves named issue packages — sheet sets tagged with issue metadata."""

    _PACKAGES_SUBDIR = 'issue_packages'

    @classmethod
    def _dir(cls):
        d = os.path.join(Config.VIEWSETS_DIR, cls._PACKAGES_SUBDIR)
        if not os.path.exists(d):
            os.makedirs(d)
        return d

    @classmethod
    def get_all_packages(cls):
        packages = []
        try:
            for filename in os.listdir(cls._dir()):
                if filename.endswith('.json'):
                    packages.append(filename.replace('.json', ''))
        except Exception:
            pass
        return sorted(packages)

    @classmethod
    def save_package(cls, name, sheet_ids, purpose, issue_date, revision):
        """Save a named issue package with metadata."""
        try:
            filepath = os.path.join(cls._dir(), '{}.json'.format(name))
            data = {
                'name': name,
                'sheet_ids': [str(Utils._get_element_id_value(sid)) for sid in sheet_ids],
                'purpose': purpose,
                'issue_date': issue_date,
                'revision': revision,
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def load_package(cls, name):
        """Returns (sheet_ids, metadata_dict) or ([], {})."""
        try:
            filepath = os.path.join(cls._dir(), '{}.json'.format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                ids = [DB.ElementId(int(sid)) for sid in data.get('sheet_ids', [])]
                meta = {k: data.get(k, '') for k in ('purpose', 'issue_date', 'revision', 'created')}
                return ids, meta
        except Exception:
            pass
        return [], {}

    @classmethod
    def delete_package(cls, name):
        try:
            filepath = os.path.join(cls._dir(), '{}.json'.format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            pass
        return False


class ExportProfileManager:
    """Saves complete export profiles (full configuration)."""
    
    @staticmethod
    def get_all_profiles():
        profiles = []
        try:
            if os.path.exists(Config.EXPORT_PROFILES_DIR):
                for filename in os.listdir(Config.EXPORT_PROFILES_DIR):
                    if filename.endswith('.json'):
                        profiles.append(filename.replace('.json', ''))
        except Exception:
            pass
        return sorted(profiles)
    
    @staticmethod
    def save_profile(name, form_instance):
        """Guarda perfil completo de exportación"""
        try:
            filepath = os.path.join(Config.EXPORT_PROFILES_DIR, "{}.json".format(name))
            
            # Safely get values from form_instance
            naming_data = form_instance.naming_builder.to_dict() if hasattr(form_instance, 'naming_builder') else {}
            output_folder = getattr(form_instance, 'output_folder', '')
            
            formats = {
                'pdf': form_instance.chk_pdf.Checked if hasattr(form_instance, 'chk_pdf') else True,
                'dwg': form_instance.chk_dwg.Checked if hasattr(form_instance, 'chk_dwg') else False,
                'dxf': form_instance.chk_dxf.Checked if hasattr(form_instance, 'chk_dxf') else False,
            }
            
            current_preset = getattr(form_instance, 'current_preset', 'Standard')
            is_exporting_views = getattr(form_instance, 'is_exporting_views', False)
            active_only = form_instance.chk_active_only.Checked if hasattr(form_instance, 'chk_active_only') else False
            sort_column = getattr(form_instance, 'current_sort_column', None)
            sort_ascending = getattr(form_instance, 'current_sort_ascending', True)

            data = {
                'name': name,
                'version': Config.VERSION,
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'naming': naming_data,
                'output_folder': output_folder,
                'formats': formats,
                'preset': current_preset,
                'is_exporting_views': is_exporting_views,
                'active_only': active_only,
                'sort_column': sort_column,
                'sort_ascending': sort_ascending
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error("Error guardando perfil de exportación", e)
            return False
    
    @staticmethod
    def load_profile(name, form_instance):
        """Carga perfil completo de exportación"""
        try:
            filepath = os.path.join(Config.EXPORT_PROFILES_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                # Cargar nomenclatura
                if 'naming' in data and hasattr(form_instance, 'naming_builder'):
                    form_instance.naming_builder.from_dict(data['naming'])
                    if hasattr(form_instance, 'txt_separator'):
                        form_instance.txt_separator.Text = form_instance.naming_builder.separator
                    if hasattr(form_instance, 'UpdateTemplateList'):
                        form_instance.UpdateTemplateList()
                
                # Cargar carpeta de salida
                if 'output_folder' in data:
                    form_instance.output_folder = data['output_folder']
                    if hasattr(form_instance, 'txt_folder'):
                        form_instance.txt_folder.Text = form_instance.output_folder
                
                # Cargar formatos
                if 'formats' in data:
                    formats = data['formats']
                    if hasattr(form_instance, 'chk_pdf'): form_instance.chk_pdf.Checked = formats.get('pdf', True)
                    if hasattr(form_instance, 'chk_dwg'): form_instance.chk_dwg.Checked = formats.get('dwg', False)
                    if hasattr(form_instance, 'chk_dxf'): form_instance.chk_dxf.Checked = formats.get('dxf', False)
                
                # Load preset
                if 'preset' in data:
                    preset = data['preset']
                    if preset == "Quick" and hasattr(form_instance, 'rb_quick'):
                        form_instance.rb_quick.Checked = True
                    elif preset == "Standard" and hasattr(form_instance, 'rb_standard'):
                        form_instance.rb_standard.Checked = True
                    elif preset == "Print" and hasattr(form_instance, 'rb_print'):
                        form_instance.rb_print.Checked = True
                    form_instance.current_preset = preset
                
                # Cargar modo de exportación
                if 'is_exporting_views' in data:
                    form_instance.is_exporting_views = data['is_exporting_views']
                    if hasattr(form_instance, 'rb_views'):
                        form_instance.rb_views.Checked = data['is_exporting_views']
                    if hasattr(form_instance, 'rb_sheets'):
                        form_instance.rb_sheets.Checked = not data['is_exporting_views']
                    if hasattr(form_instance, 'OnExportTypeChanged'):
                        form_instance.OnExportTypeChanged(None, None)
                
                # Cargar otras opciones
                if 'active_only' in data and hasattr(form_instance, 'chk_active_only'):
                    form_instance.chk_active_only.Checked = data['active_only']
                
                if 'sort_column' in data:
                    form_instance.current_sort_column = data.get('sort_column')
                    form_instance.current_sort_ascending = data.get('sort_ascending', True)
                
                return True
        except Exception as e:
            logger.error("Error cargando perfil de exportación", e)
        return False
    
    @staticmethod
    def delete_profile(name):
        try:
            filepath = os.path.join(Config.EXPORT_PROFILES_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def rename_profile(old_name, new_name):
        try:
            old_path = os.path.join(Config.EXPORT_PROFILES_DIR, "{}.json".format(old_name))
            new_path = os.path.join(Config.EXPORT_PROFILES_DIR, "{}.json".format(new_name))
            
            if os.path.exists(old_path):
                with open(old_path, 'r') as f:
                    data = json.load(f)
                
                data['name'] = new_name
                
                with open(new_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                os.remove(old_path)
                return True
        except Exception:
            pass
        return False


class NamingProfileManager:
    """Gestor de perfiles de nomenclatura"""
    
    @staticmethod
    def get_all_profiles():
        profiles = []
        try:
            if os.path.exists(Config.NAMING_PROFILES_DIR):
                for filename in os.listdir(Config.NAMING_PROFILES_DIR):
                    if filename.endswith('.json'):
                        profiles.append(filename.replace('.json', ''))
        except Exception:
            pass
        return sorted(profiles)
    
    @staticmethod
    def save_profile(name, naming_builder):
        try:
            filepath = os.path.join(Config.NAMING_PROFILES_DIR, "{}.json".format(name))
            data = {
                'name': name,
                'naming': naming_builder.to_dict(),
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False
    
    @staticmethod
    def load_profile(name):
        try:
            filepath = os.path.join(Config.NAMING_PROFILES_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    return data.get('naming', None)
        except Exception:
            pass
        return None
    
    @staticmethod
    def delete_profile(name):
        try:
            filepath = os.path.join(Config.NAMING_PROFILES_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            pass
        return False
    
    @staticmethod
    def rename_profile(old_name, new_name):
        try:
            old_path = os.path.join(Config.NAMING_PROFILES_DIR, "{}.json".format(old_name))
            new_path = os.path.join(Config.NAMING_PROFILES_DIR, "{}.json".format(new_name))
            
            if os.path.exists(old_path):
                with open(old_path, 'r') as f:
                    data = json.load(f)
                
                data['name'] = new_name
                
                with open(new_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                os.remove(old_path)
                return True
        except Exception:
            pass
        return False

class LanguageManager:
    """Gestor de configuración de idioma"""
    
    @staticmethod
    def load_language():
        try:
            if os.path.exists(Config.LANGUAGE_FILE):
                with open(Config.LANGUAGE_FILE, 'r') as f:
                    data = json.load(f)
                    return data.get('language', 'en-GB')
        except Exception:
            pass
        return 'en-GB'
    
    @staticmethod
    def save_language(language_code):
        try:
            directory = os.path.dirname(Config.LANGUAGE_FILE)
            if not os.path.exists(directory):
                os.makedirs(directory)
                
            with open(Config.LANGUAGE_FILE, 'w') as f:
                json.dump({'language': language_code}, f)
            return True
        except Exception:
            return False


class RecentExportsManager:
    """Gestor de historial de exportaciones"""
    
    @staticmethod
    def save_recent_export(results):
        """Guarda exportación con manejo mejorado de errores"""
        try:
            history = []
            if os.path.exists(Config.RECENT_EXPORTS_FILE):
                try:
                    with open(Config.RECENT_EXPORTS_FILE, 'r') as f:
                        history = json.load(f)
                except Exception:
                    history = []
            
            export_data = {
                'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'success': results.get('success', 0),
                'failed': results.get('failed', 0),
                'total': results.get('total', 0),
                'elapsed_time': round(results.get('elapsed_time', 0), 2),
                'version': Config.VERSION
            }
            
            history.insert(0, export_data)
            history = history[:20]
            
            with open(Config.RECENT_EXPORTS_FILE, 'w') as f:
                json.dump(history, f, indent=2)
                
        except Exception as e:
            logger.warning("Error guardando historial", e)
    
    @staticmethod
    def get_recent_exports():
        try:
            if os.path.exists(Config.RECENT_EXPORTS_FILE):
                with open(Config.RECENT_EXPORTS_FILE, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

