# -*- coding: utf-8 -*-
import os
import json
import datetime
from pyrevit import DB
from config import Config
from utils import Utils
from nosa_utils.logging import Logger

logger = Logger()

class ViewSetManager:
    """Gestor de conjuntos de vistas/sheets guardados"""

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


class ExportPresetManager:
    """
    Gestor de presets de exportación completos: nomenclatura + formatos +
    carpeta destino + modo de color, todo en un único conjunto con nombre.
    Sustituye al antiguo ExportProfileManager (apuntaba a controles WinForms
    que ya no existen en la UI WPF actual).
    """

    @staticmethod
    def get_all_presets():
        presets = []
        try:
            if os.path.exists(Config.EXPORT_PRESETS_DIR):
                for filename in os.listdir(Config.EXPORT_PRESETS_DIR):
                    if filename.endswith('.json'):
                        presets.append(filename.replace('.json', ''))
        except Exception:
            pass
        return sorted(presets)

    @staticmethod
    def save_preset(name, naming_builder, output_folder, subfolder, export_formats, force_black,
                     dwg_setup_name=None, combined_pdf_name=None):
        try:
            filepath = os.path.join(Config.EXPORT_PRESETS_DIR, "{}.json".format(name))
            data = {
                'name': name,
                'version': Config.VERSION,
                'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'naming': naming_builder.to_dict(),
                'output_folder': output_folder,
                'subfolder': subfolder,
                'export_formats': export_formats,
                'force_black': force_black,
                'dwg_setup_name': dwg_setup_name,
                'combined_pdf_name': combined_pdf_name,
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error("Error guardando preset de exportación", e)
            return False

    @staticmethod
    def load_preset(name):
        try:
            filepath = os.path.join(Config.EXPORT_PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error("Error cargando preset de exportación", e)
        return None

    @staticmethod
    def delete_preset(name):
        try:
            filepath = os.path.join(Config.EXPORT_PRESETS_DIR, "{}.json".format(name))
            if os.path.exists(filepath):
                os.remove(filepath)
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
