# -*- coding: utf-8 -*-
import os
import json

_CONFIGS_DIR = os.path.join(
    os.getenv('APPDATA', ''),
    'pyRevit', 'Extensions', 'NOSA.extension', 'NOSA_Configs'
)
_USAGE_FILE = os.path.join(_CONFIGS_DIR, '_usage.json')


def _load():
    try:
        with open(_USAGE_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    try:
        if not os.path.isdir(_CONFIGS_DIR):
            os.makedirs(_CONFIGS_DIR)
        with open(_USAGE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def record(plugin_key):
    """Increment the launch count for plugin_key."""
    data = _load()
    data[plugin_key] = data.get(plugin_key, 0) + 1
    _save(data)


def get_all():
    """Return dict of {plugin_key: count}."""
    return _load()


def get_top(n=10):
    """Return list of (plugin_key, count) sorted by count desc."""
    data = _load()
    return sorted(data.items(), key=lambda kv: kv[1], reverse=True)[:n]


def reset(plugin_key=None):
    """Reset count for one plugin, or all if plugin_key is None."""
    if plugin_key is None:
        _save({})
    else:
        data = _load()
        data.pop(plugin_key, None)
        _save(data)
