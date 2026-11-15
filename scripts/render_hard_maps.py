"""Render independently authored Hard landscapes, one reviewed map at a time."""
import argparse
from importlib import import_module
from pathlib import Path
import xml.etree.ElementTree as ET

from scripts.build_hard_maps import REGIONS
from scripts.hard_geography import geography
from memorybenchmark.prototypes.station_capability import load_design

ROOT=Path(__file__).resolve().parents[1]
STATIC=ROOT/'memorybenchmark/static'
NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)


def terrain(theme,geo=None):
    geo=geo or geography(theme)
    return import_module('scripts.hard_geography.'+theme).terrain(geo,REGIONS[theme]['name'])


def public_svg(geo,background):
    root=ET.fromstring(background)
    root.find('{'+NS+'}title').text+=' · 完整公开路网'
    group=ET.SubElement(root,'{'+NS+'}g',{'font-family':'Microsoft YaHei,Noto Sans CJK SC,sans-serif'})
    def el(tag,attrs,text=None):
        # Two passes also work in PDF/SVG renderers without paint-order support.
        if tag=='text' and attrs.get('stroke'):
            halo=ET.SubElement(group,'{'+NS+'}text',{k:str(v) for k,v in attrs.items() if k!='paint-order'})
            halo.set('fill','none');halo.text=str(text)
            attrs={k:v for k,v in attrs.items() if k not in ('stroke','stroke-width','paint-order')}
        item=ET.SubElement(group,'{'+NS+'}'+tag,{k:str(v) for k,v in attrs.items()})
        if text is not None:item.text=str(text)
        return item
    loc=geo['locations']
    for a,b,w in geo['edges']:
        p,q=loc[a],loc[b];d=f'M{p["x"]} {p["y"]}L{q["x"]} {q["y"]}'
        el('path',{'d':d,'stroke':'#f6f0db','stroke-width':11,'fill':'none'})
        el('path',{'d':d,'stroke':'#75816e','stroke-width':4,'fill':'none'})
        el('text',{'x':(p['x']+q['x'])/2+10,'y':(p['y']+q['y'])/2-8,'font-size':23,
                   'fill':'#536b5a','stroke':'#f4efdd','stroke-width':6,'paint-order':'stroke'},w)
    for key,n in loc.items():
        x,y=n['x'],n['y'];kind=n['kind']
        if kind=='station':el('rect',{'x':x-16,'y':y-16,'width':32,'height':32,'rx':4,'fill':'#fbf8e8','stroke':'#355b52','stroke-width':4})
        elif kind=='camp':el('path',{'d':f'M{x} {y-24}l25 43h-50Z','fill':'#355b52','stroke':'#f9f5e2','stroke-width':4})
        else:el('circle',{'cx':x,'cy':y,'r':6 if n.get('transit') else 14 if kind=='survey' else 8,'fill':'#fcf8e9','stroke':'#637a66','stroke-width':3})
        if not n.get('transit'):
            el('text',{'x':x,'y':y-30,'font-size':29 if kind in ('station','survey','camp') else 21,
                       'text-anchor':'middle','fill':'#294d44','stroke':'#f5f0dc','stroke-width':7,'paint-order':'stroke'},key)
    for r in geo['regions']:
        el('text',{'x':r['x'],'y':r['y'],'font-size':42,'text-anchor':'middle','fill':'#68795e','opacity':'.7'},r['name'])
    ET.indent(root)
    return ET.tostring(root,encoding='unicode')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map',choices=tuple(REGIONS))
    parser.add_argument('--draft',type=Path,help='Write a source-geography preview without changing installed assets')
    args=parser.parse_args()
    for theme in ([args.map] if args.map else REGIONS):
        geo=geography(theme);background=terrain(theme,geo)
        if args.draft:
            args.draft.mkdir(parents=True,exist_ok=True)
            (args.draft/(theme+'-terrain.svg')).write_text(background+'\n',encoding='utf-8')
            (args.draft/(theme+'-complete.svg')).write_text(public_svg(geo,background)+'\n',encoding='utf-8')
        else:
            design=load_design(ROOT/'memorybenchmark/data'/(theme+'_hard48.json'))
            if design['public']['locations']!=geo['locations'] or design['public']['edges']!=geo['edges']:
                raise ValueError('Build and validate this map version before rendering final assets: '+theme)
            out=ROOT/'docs/assets/hard-maps';out.mkdir(parents=True,exist_ok=True)
            (STATIC/(REGIONS[theme]['terrain']+'-terrain.svg')).write_text(background+'\n',encoding='utf-8')
            (out/(theme+'-complete.svg')).write_text(public_svg(geo,background)+'\n',encoding='utf-8')
        print('Rendered independent geography:',theme,'model calls: 0')


if __name__=='__main__':main()
