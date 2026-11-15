"""Compile the existing display SVG geography for worker-tiled GPU rendering.

Scientific inputs and geographic source assets are read-only. Coordinate
precision is one metre; disconnected features stay independent for tile culling.
"""
from pathlib import Path
from math import atan,exp,pi,degrees,log2
from hashlib import sha256
import json,gzip,re
import xml.etree.ElementTree as ET
from shapely.geometry import Polygon,LineString,box,mapping
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1];STATIC=ROOT/'memorybenchmark/static'
NUMBER=r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'

def inverse(x,y):return [round(x/1000-180,5),round(degrees(2*atan(exp((180-y/1000)*pi/180))-pi/2),5)]

def rings(element):
    if element.tag.endswith('polygon'):
        n=list(map(float,re.findall(NUMBER,element.get('points',''))));return [(list(zip(n[::2],n[1::2])),True)]
    # All generated display paths use absolute M/L/Z, verified by the source builder.
    result=[]
    for part in re.findall('[Mm][^Mm]*',element.get('d','')):
        n=list(map(float,re.findall(NUMBER,part)));points=list(zip(n[::2],n[1::2]))
        if len(points)>1:result.append((points,'z' in part.lower()))
    return result

def geometries(element):
    pending=None;outer_sign=None
    for pts,closed in rings(element):
        if not closed:
            if pending is not None:yield Polygon(pending[0],pending[1:]);pending=None
            yield LineString(pts);continue
        # EPSG:3857 screen y increases south: exterior winding is negative.
        area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(pts,pts[1:]+pts[:1]))
        if outer_sign is None:outer_sign=1 if area>0 else -1
        if area*outer_sign>0 or pending is None:
            if pending is not None:yield Polygon(pending[0],pending[1:])
            pending=[pts]
        else:pending.append(pts)
    if pending is not None:yield Polygon(pending[0],pending[1:])

def compile_asset(asset,bounds=None):
    root=ET.parse(STATIC/asset.lstrip('/')).getroot();features=[]
    defs=set(e for parent in root.iter() if parent.tag.endswith(('defs','clipPath')) for e in parent.iter())
    clips={}
    for element in root.iter():
        if element.tag.endswith('clipPath'):
            parts=[g for child in element for g in geometries(child)]
            clips[element.get('id')]=unary_union([g if g.is_valid else g.buffer(0) for g in parts])
    if bounds:
        x,y,w,h=bounds;outer=box(x,y,x+w,y+h);inner=box(x+w*.12,y+h*.12,x+w*.88,y+h*.88)
        zones=[]
        previous=outer
        for i in range(1,9):
            t=i/8;current=box(x+w*.12*t,y+h*.12*t,x+w-w*.12*t,y+h-h*.12*t)
            zones.append((previous.difference(current),((i-.5)/8)));previous=current
        zones.append((inner,1))
    for element in root.iter():
        if element in defs or not element.tag.endswith(('path','polygon')):continue
        fill=element.get('fill','#eee8d5');stroke=element.get('stroke','none');fixed=element.get('vector-effect')=='non-scaling-stroke'
        props={'fill':fill,'stroke':stroke,'opacity':float(element.get('opacity',1)),'fillOpacity':float(element.get('fill-opacity',1)),'width':float(element.get('stroke-width',0)),'fixed':fixed,'kind':element.get('data-feature','regional')}
        if asset=='/world-overview.svg' and stroke!='none':props.update(fixed=True,width=.65)
        for g in geometries(element):
            if g.is_empty:continue
            if not g.is_valid:g=g.buffer(0)
            clip=re.fullmatch(r'url\(#([^)]*)\)',element.get('clip-path',''))
            if clip:g=g.intersection(clips[clip.group(1)])
            if g.is_empty:continue
            parts=[(g,1)]
            if bounds and not inner.covers(g):
                parts=[(g.intersection(zone),alpha) for zone,alpha in zones if zone.intersects(g)]
            for piece,alpha in parts:
                for geom in getattr(piece,'geoms',[piece]):
                    if geom.is_empty or geom.geom_type not in ('Polygon','LineString'):continue
                    gj=mapping(geom)
                    a,b,c,d=geom.bounds;span=max(c-a,d-b,.00001)
                    minimum=0 if props['kind']=='kgari-coastline' else max(0,round(log2(360000*(1.8 if geom.geom_type=='Polygon' else 3)/(512*span)),2))
                    def coords(v):
                        if isinstance(v[0],(int,float)):return inverse(*v)
                        return [coords(p) for p in v]
                    features.append({'type':'Feature','properties':{**props,'opacity':round(props['opacity']*alpha,4),'minZoom':minimum},'geometry':{'type':gj['type'],'coordinates':coords(gj['coordinates'])}})
    data=json.dumps({'type':'FeatureCollection','features':features},ensure_ascii=True,separators=(',',':')).encode()
    name='atlas-geo-'+sha256(data).hexdigest()[:16]+'.geojson';p=STATIC/name;p.write_bytes(data);p.with_suffix('.geojson.gz').write_bytes(gzip.compress(data,9,mtime=0))
    return {'url':'/'+name,'features':len(features),'source_svg':asset,'source_sha256':sha256((STATIC/asset.lstrip('/')).read_bytes()).hexdigest(),'sha256':sha256(data).hexdigest(),'bytes':len(data)}

def build():
    atlas=json.loads((STATIC/'world-atlas.json').read_text(encoding='utf-8'))
    record={'protocol':'human-atlas-gpu-1','overview':compile_asset(atlas['world_asset']),'coast':compile_asset(atlas['layers']['coast']['asset']),'physical':compile_asset(atlas['layers']['physical']['asset']),'regions':{}}
    for r in atlas['regions']:
        entry={'detail':compile_asset(r['terrain_asset'],r.get('terrain_view_box'))}
        if r.get('context'):entry['context']=compile_asset(r['context']['asset'],r['context']['view_box'])
        record['regions'][r['id']]=entry
    (STATIC/'world-gpu.json').write_text(json.dumps(record,separators=(',',':')),encoding='utf-8')
    return {'regions':12,'sources':3+sum(len(r) for r in record['regions'].values()),'features':sum(v['features'] for v in [record['overview'],record['coast'],record['physical']])+sum(v['features'] for r in record['regions'].values() for v in r.values())}

if __name__=='__main__':print(json.dumps(build()),flush=True)
