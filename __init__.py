"""hermes-evol plugin — re-exports register() from the hermes_evol package."""
import sys as _sys
import os as _os

# Hermes plugin loader does NOT add the plugin directory to sys.path.
# Without this, 'from hermes_evol.plugin import register' fails with
# ModuleNotFoundError: No module named 'hermes_evol'
_plugin_dir = _os.path.dirname(_os.path.abspath(__file__))
if _plugin_dir not in _sys.path:
    _sys.path.insert(0, _plugin_dir)

from hermes_evol.plugin import register
