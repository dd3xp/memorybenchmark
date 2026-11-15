"""Six individual Easy/Normal landscapes; no shared road-layout generator."""
from importlib import import_module

THEMES=('capulin','forest','cascade','nessie','dingo','boar')

def geography(theme):
    if theme not in THEMES:raise ValueError('Unknown field landscape: '+theme)
    return import_module('scripts.field_geography.'+theme).build()
