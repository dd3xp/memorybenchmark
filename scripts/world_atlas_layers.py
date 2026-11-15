"""Scale-dependent human basemap layers, from real geographic source geometry."""
from pathlib import Path
from collections import defaultdict
from hashlib import sha256
import json
import xml.etree.ElementTree as ET
from shapely.geometry import shape, Polygon, Point, box
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union
from scripts.build_world_atlas import project, NS, WORLD

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'.runs/atlas-world-lod-20261108/reference'
OLD=ROOT/'.runs/atlas-cartographic-style-20261107/reference-data'
STATIC=ROOT/'memorybenchmark/static'
LAND='#eee8d5';WATER='#a9c7ca'

def svg_root(bounds=WORLD):
    return ET.Element('{'+NS+'}svg',{'viewBox':' '.join(map(str,bounds)), 'data-world-projection':'EPSG:3857'})

def geometry_path(g,precision=2):
    def line(coords,closed=False):
        return 'M'+'L'.join(f'{x:.{precision}f} {y:.{precision}f}' for x,y in (project(*v[:2]) for v in coords))+('Z' if closed else '')
    if g.is_empty:return ''
    if g.geom_type=='Polygon':
        g=orient(g)
        return line(g.exterior.coords,True)+''.join(line(r.coords,True) for r in g.interiors)
    if g.geom_type in ('LineString','LinearRing'):return line(g.coords)
    return ''.join(geometry_path(v,precision) for v in getattr(g,'geoms',[]))

def write(name,root):
    ET.SubElement(root,'{'+NS+'}desc').text='Human display only. Natural Earth 5.1.2 public domain; © OpenStreetMap contributors, ODbL.'
    p=STATIC/name;p.write_text(ET.tostring(root,encoding='unicode'),encoding='utf-8')
    return {'asset':'/'+name,'sha256':sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}

def feature_path(root,g,kind,**attrs):
    return ET.SubElement(root,'{'+NS+'}path',{'d':geometry_path(g),'data-feature':kind,**attrs})

def grouped(root,groups):
    styles={
        'forest':{'fill':'#b8c9aa','fill-opacity':'.5','stroke':'none'},
        'terrain':{'fill':'#d5c29f','fill-opacity':'.34','stroke':'none'},
        'settlement':{'fill':'#bd9971','fill-opacity':'.28','stroke':'none'},
        'water':{'fill':WATER,'stroke':'#8eafb1','stroke-width':'.45'},
        'river':{'fill':'none','stroke':'#91b3b6','stroke-width':'.8'},
        'major-road':{'fill':'none','stroke':'#b5ac92','stroke-width':'.9','opacity':'.75'},
        'minor-road':{'fill':'none','stroke':'#b8b29c','stroke-width':'.65','opacity':'.45'},
    }
    for kind in ('forest','terrain','settlement','major-road','minor-road','river','water'):
        if groups.get(kind):
            ET.SubElement(root,'{'+NS+'}path',{'d':''.join(groups[kind]),'data-feature':kind,'vector-effect':'non-scaling-stroke','stroke-linecap':'round','stroke-linejoin':'round',**styles[kind]})

def feather(root,bounds):
    # Only diffuse contextual landcover at the distant edge of the source window.
    # The actual experiment area is well inside the fully opaque centre.
    x,y,w,h=bounds;defs=ET.SubElement(root,'{'+NS+'}defs')
    for axis in ('x','y'):
        grad=ET.SubElement(defs,'{'+NS+'}linearGradient',{'id':'edge-'+axis,'x1':'0','y1':'0','x2':'1' if axis=='x' else '0','y2':'1' if axis=='y' else '0'})
        for pos,opacity in ((0,0),(.12,1),(.88,1),(1,0)):
            ET.SubElement(grad,'{'+NS+'}stop',{'offset':str(pos),'stop-color':'white','stop-opacity':str(opacity)})
    for axis in ('x','y'):
        mask=ET.SubElement(defs,'{'+NS+'}mask',{'id':'mask-'+axis,'maskUnits':'userSpaceOnUse','x':str(x),'y':str(y),'width':str(w),'height':str(h)})
        ET.SubElement(mask,'{'+NS+'}rect',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'fill':'url(#edge-'+axis+')'})
    a=ET.SubElement(root,'{'+NS+'}g',{'mask':'url(#mask-x)'})
    return ET.SubElement(a,'{'+NS+'}g',{'mask':'url(#mask-y)'})

def dingo_land():
    from scripts.build_geographic_atlas import geometry
    rows=json.loads((OLD/'dingo-osm.json').read_bytes())['elements']
    lines=[]
    for r in rows:
        if r.get('tags',{}).get('natural')!='coastline':continue
        g=geometry(r)
        if g is not None:lines.append(g.exterior if g.geom_type=='Polygon' else g)
    candidates=[g for g in polygonize(unary_union(lines)) if g.covers(Point(153.08,-25.45))]
    assert candidates,'The complete K’gari coastline must be present before any local detail loads.'
    return max(candidates,key=lambda g:g.area)

def build_layers(entries):
    from scripts.build_geographic_atlas import geometry
    island=dingo_land();coast=svg_root()
    ET.SubElement(coast,'{'+NS+'}rect',{'width':'360000','height':'360000','fill':WATER})
    land=[]
    for f in json.loads((REF/'ne_10m_land.geojson').read_bytes())['features']:
        g=shape(f['geometry'])
        for part in getattr(g,'geoms',[g]):
            # Replace the generalized island with the exact same full OSM coast
            # used by its local atlas. Never gate the island behind local LOD.
            if part.area<1 and part.intersects(island):continue
            land.append(part.simplify(.001,preserve_topology=True))
    ET.SubElement(coast,'{'+NS+'}path',{'d':''.join(geometry_path(g) for g in land),'fill':LAND})
    feature_path(coast,island,'kgari-coastline',fill=LAND,**{'data-source':'OpenStreetMap full K’gari island'})
    coast_record=write('world-coast.svg',coast)
    physical=svg_root();groups=defaultdict(list)
    for file,kind in (('ne_10m_urban_areas.geojson','settlement'),('ne_10m_rivers_lake_centerlines.geojson','river'),('ne_10m_lakes.geojson','water')):
        for f in json.loads((REF/file).read_bytes())['features']:
            g=shape(f['geometry']).simplify(.003,preserve_topology=True)
            if kind=='settlement' and g.area<.003:continue
            groups[kind].append(geometry_path(g))
    grouped(physical,groups);physical_record=write('world-physical.svg',physical)
    places=[]
    raw=ROOT/'.runs/atlas-lunatic-whole-region-20261107/research/ne_10m_populated_places_simple.geojson'
    for f in json.loads(raw.read_bytes())['features']:
        p=f['properties'];lon,lat=f['geometry']['coordinates'];x,y=project(lon,lat)
        places.append({'name':p.get('name_zh') or p.get('name') or p.get('name_en'),'x':x,'y':y,'rank':p.get('scalerank',10),'population':p.get('pop_max',0)})
    context_records=[]
    for entry in entries:
        theme=entry['id'].split('-')[0]
        source=REF/(theme+'-context.json')
        if not source.exists():continue  # Large Lunatic regions use global physical geography.
        meta=json.loads(source.with_suffix('.source.json').read_bytes());w,s,e,n=meta['bbox']
        # The original dingo source includes its entire island, not just the game rectangle.
        if theme=='dingo':w,s,e,n=min(w,152.94),min(s,-25.82),max(e,153.38),max(n,-24.68)
        a,b=project(w,n);c,d=project(e,s);bounds=[a,b,c-a,d-b]
        rows={ (r['type'],r['id']):r for r in json.loads(source.read_bytes())['elements'] }
        originals=json.loads((OLD/(theme+'-osm.json')).read_bytes())['elements']
        rows.update({(r['type'],r['id']):r for r in originals})
        groups=defaultdict(list);fine=defaultdict(list);count=0
        extent=box(w,s,e,n)
        for row in rows.values():
            t=row.get('tags',{});kind=None
            if row['type']=='node':
                if t.get('place') and t.get('name'):
                    x,y=project(row['lon'],row['lat']);places.append({'name':t.get('name:zh') or t.get('name:en') or t['name'],'x':x,'y':y,'rank':8 if t['place']=='village' else 6,'population':int(t.get('population','0').replace(',','')) if t.get('population','0').replace(',','').isdigit() else 0})
                continue
            if t.get('natural')=='water' or t.get('waterway')=='riverbank':kind='water'
            elif t.get('waterway') in ('river','stream','canal'):kind='river'
            elif t.get('natural') in ('wood','scrub') or t.get('landuse')=='forest':kind='forest'
            elif t.get('natural') in ('sand','bare_rock') or t.get('landuse') in ('farmland','meadow'):kind='terrain'
            elif t.get('landuse')=='residential':kind='settlement'
            elif t.get('highway'):kind='major-road' if t['highway'] in ('motorway','trunk','primary','secondary','tertiary') else 'minor-road'
            if not kind:continue
            g=geometry(row)
            if g is None or g.is_empty:continue
            g=g.intersection(extent).simplify(.000015,preserve_topology=True)
            if g.is_empty:continue
            if kind in ('forest','terrain','settlement') and g.area<.0000002:continue
            (fine if kind=='minor-road' else groups)[kind].append(geometry_path(g));count+=1
        context=svg_root(bounds);grouped(feather(context,bounds),groups)
        filename=entry['map'].get('terrain','') or entry['terrain_asset'].rsplit('/',1)[-1].replace('-world.svg','')
        record=write(filename+'-context.svg',context)
        entry['context']={'asset':record['asset'],'view_box':bounds,'source_sha256':meta['sha256'],'features':count}
        # Fine roads share the surrounding geometry; no clipped beige tile or
        # local footer is composited over the world.
        detail=svg_root(bounds);grouped(feather(detail,bounds),fine)
        write(entry['terrain_asset'].lstrip('/'),detail)
        entry['terrain_view_box']=bounds
        entry['detail_source']='Original OSM reference geometry plus wider OSM context'
        context_records.append(record)
    sources={p.name:sha256(p.read_bytes()).hexdigest() for p in REF.glob('*.json') if not p.name.endswith('.source.json')}
    return {'coast':coast_record,'physical':physical_record,'context_assets':context_records,'places':places,'palette':{'land':LAND,'water':WATER},'source_sha256':sources,'kgari_coast_always_present':True}
