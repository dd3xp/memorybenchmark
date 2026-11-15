"""Three individually authored regional landscapes, sharing no road template."""
from importlib import import_module
THEMES=('scandinavia','mongolia','andes')
def geography(theme):
    if theme not in THEMES:raise ValueError(theme)
    return import_module('scripts.lunatic_geography.whole_region').build(theme)
