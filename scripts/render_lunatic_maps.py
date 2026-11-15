"""Render one authored Lunatic landscape; never edit experiment outputs."""
from importlib import import_module
from pathlib import Path
import argparse
from scripts.lunatic_geography import THEMES,geography
from scripts.build_lunatic_maps import REGIONS
from scripts.render_hard_maps import public_svg
from memorybenchmark.prototypes.station_capability import load_design
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',choices=THEMES,required=True);a=p.parse_args()
    geo=geography(a.map);d=load_design(ROOT/'memorybenchmark/data'/(a.map+'_lunatic64.json'))
    for k in ('locations','edges','view_box'):assert geo[k]==d['public'][k]
    from scripts.lunatic_geography.whole_region_render import terrain as background, complete
    terrain=background(geo,d['public']['name'])
    out=ROOT/'docs/assets/lunatic-maps';out.mkdir(parents=True,exist_ok=True)
    (ROOT/'memorybenchmark/static'/(REGIONS[a.map]['terrain']+'-terrain.svg')).write_text(terrain+'\n',encoding='utf-8')
    (out/(a.map+'-complete.svg')).write_text(complete(geo,d['public']['name'])+'\n',encoding='utf-8')
    print('Rendered',a.map)
if __name__=='__main__':main()
