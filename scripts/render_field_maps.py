"""Render a single independently authored Easy/Normal landscape."""
from importlib import import_module
from pathlib import Path
import argparse
from scripts.field_geography import THEMES,geography
from scripts.build_field_maps import FILES
from scripts.render_hard_maps import public_svg
from memorybenchmark.prototypes.station_capability import load_design

ROOT=Path(__file__).resolve().parents[1]

def render(theme,draft=None):
    geo=geography(theme);path=ROOT/'memorybenchmark/data'/(FILES[theme]+'.json')
    design=load_design(path);background=import_module('scripts.field_geography.'+theme).terrain(geo,design['public']['name'])
    if draft:
        output=draft;output.mkdir(parents=True,exist_ok=True)
        (output/(theme+'-terrain.svg')).write_text(background+'\n',encoding='utf-8')
    else:
        for field in ('locations','edges','view_box'):
            if geo[field]!=design['public'][field]:raise ValueError('Build the reviewed map before installing terrain: '+theme)
        output=ROOT/'docs/assets/difficulty-maps'
        (ROOT/'memorybenchmark/static'/(design['public']['terrain']+'-terrain.svg')).write_text(background+'\n',encoding='utf-8')
    (output/(FILES[theme]+'-complete.svg')).write_text(public_svg(geo,background)+'\n',encoding='utf-8')
    print('Rendered independent field map:',theme)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--map',choices=THEMES)
    parser.add_argument('--draft',type=Path);args=parser.parse_args()
    for theme in ([args.map] if args.map else THEMES):render(theme,args.draft)

if __name__=='__main__':main()
