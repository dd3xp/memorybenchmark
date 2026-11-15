"""Reuse the twelve human atlas layers in a shared, offline real-world map.

Only presentation artifacts are written. Scientific graphs and observations
retain their original coordinates, identities, routes and task rules.
"""
from copy import deepcopy
from hashlib import sha256
from math import atan, degrees, exp, log, pi, radians, tan
from pathlib import Path
import argparse
import json
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
NS='http://www.w3.org/2000/svg'
ET.register_namespace('',NS)
SCALE=1000
WORLD=[0,0,360000,360000]

def design_fingerprint(path):
    """Hash UTF-8/LF display metadata; frozen scientific byte hashes stay raw."""
    return sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def project(lon,lat):
    lat=max(-85.05112878,min(85.05112878,lat))
    return [round((lon+180)*SCALE,7),round((180-degrees(log(tan(pi/4+radians(lat)/2))))*SCALE,7)]

def local_projection(bounds,view_box):
    west,south,east,north=bounds; x,y,w,h=view_box
    def lonlat(a,b):return west+(a-x)/w*(east-west),north-(b-y)/h*(north-south)
    def convert(a,b):return project(*lonlat(a,b))
    return convert,lonlat

def line(points,convert):
    result=[]
    for i,(x,y) in enumerate(points):
        if i:
            a,b=points[i-1]
            # Densify long regional segments before nonlinear latitude projection.
            pieces=max(1,min(80,int(abs(y-b)/180)+1))
            result.extend(convert(a+(x-a)*j/pieces,b+(y-b)*j/pieces) for j in range(1,pieces))
        result.append(convert(x,y))
    return result

def path_data(value,convert):
    tokens=re.findall(r'[MLZmlz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',value)
    allowed=set(re.findall('[A-DF-Za-df-z]',value))
    assert allowed <= set('MLZmlz'),allowed
    result=[];i=0;command=None;x=y=0;start=(0,0)
    while i<len(tokens):
        if tokens[i].isalpha():
            command=tokens[i];i+=1
            if command.upper()=='Z':result.append('Z');x,y=start;continue
        a,b=float(tokens[i]),float(tokens[i+1]);i+=2
        if command.islower():a+=x;b+=y
        px,py=convert(a,b)
        result.append(f'{command.upper()}{px:.7f} {py:.7f}')
        x,y=a,b
        if command.upper()=='M':start=(x,y);command='l' if command=='m' else 'L'
    return ''.join(result)

def regional_svg(source,convert,box,lunatic=False):
    root=ET.parse(source).getroot()
    old_box=list(map(float,root.get('viewBox').split()))
    sample=convert(old_box[0]+old_box[2]/2,old_box[1]+old_box[3]/2)
    next_x=convert(old_box[0]+old_box[2]/2+1,old_box[1]+old_box[3]/2)
    factor=abs(next_x[0]-sample[0])
    for parent in list(root.iter()):
        for e in list(parent):
            tag=e.tag.split('}')[-1]
            # The former in-image legend belongs to the UI, not world geography.
            if lunatic and parent is root and (tag in ('text','rect') or e.get('fill') in ('#cbd3c4','#eee8d5','#a9c7ca')):parent.remove(e)
    for e in root.iter():
        tag=e.tag.split('}')[-1]
        if tag=='path':e.set('d',path_data(e.get('d',''),convert))
        elif tag=='polygon':
            numbers=list(map(float,re.findall(r'[-+]?\d*\.?\d+',e.get('points',''))))
            points=line(list(zip(numbers[::2],numbers[1::2])),convert)
            e.set('points',' '.join(f'{a:.7f},{b:.7f}' for a,b in points))
        elif tag=='rect':
            x,y=float(e.get('x',0)),float(e.get('y',0));w,h=float(e.get('width',0)),float(e.get('height',0))
            a,b=convert(x,y);c,d=convert(x+w,y+h)
            e.set('x',str(a));e.set('y',str(b));e.set('width',str(c-a));e.set('height',str(d-b))
            if e.get('rx'):e.set('rx',str(float(e.get('rx'))*factor))
        elif tag=='text':
            a,b=convert(float(e.get('x',0)),float(e.get('y',0)));e.set('x',str(a));e.set('y',str(b))
        for attr in ('stroke-width','font-size'):
            if e.get(attr):e.set(attr,str(float(e.get(attr))*factor))
    root.set('viewBox',' '.join(map(str,box)));root.set('width',str(box[2]));root.set('height',str(box[3]))
    root.set('data-world-projection','EPSG:3857')
    desc=ET.SubElement(root,'{'+NS+'}desc');desc.text='Display projection only. Reused local atlas. Natural Earth 5.1.2 and OpenStreetMap contributors.'
    return ET.tostring(root,encoding='unicode')

def build(reference):
    from memorybenchmark.cartography import geographic_presentation
    from memorybenchmark.map_catalog import MAPS,station_design
    static=ROOT/'memorybenchmark/static'; entries=[]
    for mid,(name,variant,_) in MAPS.items():
        design=json.loads(station_design(mid).read_text(encoding='utf-8'))
        public=design['public'];layer=geographic_presentation(public)
        local={**public,**(layer or {})};vb=local['view_box']
        bounds=layer['cartographic_reference']['bbox'] if layer else design['provenance']['reference_window']['bbox_west_south_east_north']
        convert,lonlat=local_projection(bounds,vb)
        a,b=project(bounds[0],bounds[3]);c,d=project(bounds[2],bounds[1]);box=[a,b,c-a,d-b]
        source=static/((layer['terrain_asset'].lstrip('/')) if layer else public['terrain']+'-terrain.svg')
        filename=public['terrain']+'-world.svg'
        (static/filename).write_text(regional_svg(source,convert,box,lunatic=mid.endswith('lunatic')),encoding='utf-8')
        positions={}
        for key,n in local['locations'].items():
            x,y=convert(n['x'],n['y']);lon,lat=lonlat(n['x'],n['y'])
            positions[key]={**deepcopy(n),'x':x,'y':y,'longitude':round(lon,7),'latitude':round(lat,7)}
        paths={}
        for u,v,_ in public['edges']:
            key='|'.join(sorted((u,v)))
            points=local.get('edge_paths',{}).get(key,[[local['locations'][u]['x'],local['locations'][u]['y']],[local['locations'][v]['x'],local['locations'][v]['y']]])
            paths[key]=line(points,convert)
        entries.append({'id':mid,'name':name,'difficulty':public['difficulty'],'task_count':len(design['tasks']),
            'view_box':box,'geographic_bounds':bounds,'local_view_box':vb,
            'terrain_asset':'/'+filename,'source_asset':'/'+source.name,'source_asset_sha256':sha256(source.read_bytes()).hexdigest(),
            'design_sha256':design_fingerprint(station_design(mid)),
            'map':{'locations':positions,'edges':deepcopy(public['edges']),'edge_paths':paths,
                   'ferry_edges':public.get('ferry_edges',[]),'processing_regions':public.get('processing_regions',{})}})
    world=ET.Element('{'+NS+'}svg',{'viewBox':'0 0 360000 360000','data-source':'Natural Earth 5.1.2'})
    ET.SubElement(world,'{'+NS+'}rect',{'width':'360000','height':'360000','fill':'#a9c7ca'})
    def geometry(coords):
        return ''.join('M'+'L'.join(f'{x:.5f} {y:.5f}' for x,y in [project(*p) for p in ring])+'Z' for ring in coords)
    countries=[]
    for f in json.loads(reference.read_text(encoding='utf-8'))['features']:
        g=f['geometry'];p=f['properties'];polys=g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']]
        ET.SubElement(world,'{'+NS+'}path',{'d':''.join(geometry(poly) for poly in polys),'fill':'#eee8d5','stroke':'#b4baa4','stroke-width':'90','stroke-linejoin':'round'})
        lon,lat=p.get('LABEL_X'),p.get('LABEL_Y')
        if lon is not None and lat is not None:
            x,y=project(lon,lat);countries.append({'name':p.get('NAME_ZH') or p.get('NAME_EN') or p['NAME'],'x':x,'y':y,'rank':p.get('LABELRANK',6),'area':p.get('POP_EST',0)})
    from scripts.world_atlas_layers import build_layers,dingo_land,feature_path
    # The named study island is retained even in the smallest-scale overview.
    feature_path(world,dingo_land(),'kgari-coastline',fill='#eee8d5')
    layers=build_layers(entries)
    ET.SubElement(world,'{'+NS+'}desc').text='Natural Earth 5.1.2 public domain. EPSG:3857 display projection, clipped at85.05112878 latitude.'
    (static/'world-overview.svg').write_text(ET.tostring(world,encoding='unicode'),encoding='utf-8')
    record={'protocol':'human-world-atlas-1','projection':'EPSG:3857','world_box':WORLD,'world_asset':'/world-overview.svg',
        'reference':{'source':'Natural Earth 5.1.2','license':'public domain','sha256':sha256(reference.read_bytes()).hexdigest()},
        'countries':countries,'regions':entries,'layers':layers,'scientific_state_changed':False,'design_sha256_encoding':'utf-8-lf'}
    (static/'world-atlas.json').write_text(json.dumps(record,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    # Precompressed immutable geography avoids shipping tens of MB per view.
    # The browser has a plain-SVG fallback; the web server needs no new behavior.
    import gzip
    assets=['world-atlas.json','world-overview.svg','world-coast.svg','world-physical.svg']
    assets += [e['terrain_asset'].lstrip('/') for e in entries]
    assets += [e['context']['asset'].lstrip('/') for e in entries if e.get('context')]
    for asset in assets:(static/(asset+'.gz')).write_bytes(gzip.compress((static/asset).read_bytes(),compresslevel=9,mtime=0))
    return {'maps':len(entries),'locations':sum(len(e['map']['locations']) for e in entries),'world_metadata_bytes':(static/'world-atlas.json').stat().st_size}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reference',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().reference)))
