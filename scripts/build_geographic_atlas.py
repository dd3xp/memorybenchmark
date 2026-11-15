"""Make human-only, WGS84-backed map presentations without changing game data."""
from pathlib import Path
from collections import Counter
from hashlib import sha256
from math import cos, radians, hypot
import json, sys, xml.etree.ElementTree as ET
import numpy as np
from scipy.interpolate import RBFInterpolator
from shapely.geometry import Polygon, LineString, Point, box, MultiPolygon
from shapely.ops import unary_union, polygonize, nearest_points

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from memorybenchmark.map_catalog import MAPS
from scripts.field_geography import geography as field_geo
from scripts.hard_geography import geography as hard_geo

S=ROOT/'.runs/atlas-cartographic-style-20261107';RAW=S/'reference-data'
OUT=ROOT/'memorybenchmark/cartographic_maps';OUT.mkdir(exist_ok=True)
NS='http://www.w3.org/2000/svg';ET.register_namespace('',NS)

SPECS={
 'capulin':{'bbox':[-103.993,36.771,-103.958,36.790], 'anchors':[
  [1370,600,-103.97035,36.78250], [900,1530,-103.9791,36.7755],
  [1700,250,-103.9668,36.7851], [300,1200,-103.9871,36.7773]]},
 'forest':{'bbox':[-122.596,37.888,-122.568,37.912], 'anchors':[
  [1100,0,-122.5842,37.9077], [1100,1600,-122.5783,37.892],
  [350,750,-122.5905,37.8995]]},
 'cascade':{'bbox':[15.588,44.855,15.630,44.914], 'lakes':[
  [1425,440,'Kozjak'],[1140,750,'Gradinsko jezero'],
  [850,1060,'Galovac'],[565,1350,'Prošćansko jezero']]},
 'nessie':{'bbox':[-5.0,56.99,-4.08,57.59], 'lake_alignment':'Loch Ness'},
 'dingo':{'bbox':[153.003,-25.555,153.163,-25.394], 'lakes':[
  [940,580,'Lake McKenzie'],[2020,630,'Lake Wabby'],[1100,1810,'Lake Birrabeen']],
  'anchors':[[1500,1200,153.0547,-25.4762]]},
 'boar':{'bbox':[-2.58,51.746,-2.455,51.837], 'anchors':[
  [900,0,-2.542,51.805], [2420,0,-2.504,51.815],
  [1690,2040,-2.482,51.764]]},
 'orcia':{'bbox':[11.43,42.94,11.75,43.09], 'anchors':[
  [520,880,11.4902818,43.0575578],[2250,900,11.6042,43.0599],
  [3700,720,11.6789076,43.0765485], [2850,2740,11.6155411,43.0071166],
  [600,2780,11.4604941,42.9939571]]},
 'hampi':{'bbox':[76.41,15.265,76.56,15.365], 'anchors':[
  [2010,2770,76.4734,15.3155],[3540,3250,76.4860,15.2810],
  [890,1090,76.4580,15.3350],[2690,840,76.4831,15.3387]]},
 'angkor':{'bbox':[103.76,13.365,103.97,13.485], 'anchors':[
  [1350,1740,103.8021,13.4312], [5530,1140,103.9185,13.4395],
  [3500,2000,103.8584,13.4431],[3470,3500,103.8666,13.4125]]},
}

def digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()

def geometry(e):
    if e['type']=='node':return Point(e['lon'],e['lat'])
    if e['type']=='way':
        pts=[(p['lon'],p['lat']) for p in e.get('geometry',[]) if 'lon' in p]
        if len(pts)<2:return None
        if pts[0]==pts[-1] and len(pts)>3:return Polygon(pts).buffer(0)
        return LineString(pts)
    lines=[]
    for m in e.get('members',[]):
        pts=[(p['lon'],p['lat']) for p in m.get('geometry',[]) if 'lon' in p]
        if len(pts)>1 and m.get('role')!='inner':lines.append(LineString(pts))
    return unary_union(list(polygonize(unary_union(lines)))) if lines else None

def make(theme):
    spec=SPECS[theme];w,s,e,n=spec['bbox'];latitude=(s+n)/2
    width=6000;factor=width/((e-w)*cos(radians(latitude)));height=(n-s)*factor
    def project(lon,lat):return np.array([(lon-w)*cos(radians(latitude))*factor,(n-lat)*factor])
    def inverse(x,y):return [round(w+x/factor/cos(radians(latitude)),7),round(n-y/factor,7)]
    clip=box(0,0,width,height)
    source=json.loads((RAW/(theme+'-source.json')).read_text())
    elements=json.loads((RAW/(theme+'-osm.json')).read_text())['elements']
    shapes=[];names={}
    for row in elements:
        g=geometry(row)
        if g is None or g.is_empty:continue
        t=row.get('tags',{});name=t.get('name')
        if name and (name not in names or g.area>names[name][1].area):names[name]=(row,g)
        shapes.append((row,g))
    mid=next(k for k in MAPS if k.startswith(theme+'-'))
    filename=MAPS[mid][2];design=json.loads((ROOT/'memorybenchmark/data'/filename).read_text(encoding='utf-8'))
    public=design['public'];geo=(hard_geo if theme in ('orcia','hampi','angkor') else field_geo)(theme)
    ow,oh=public['view_box'][2:];anchors=list(spec.get('anchors',[]))
    for x,y,name in spec.get('lakes',[]):
        if name not in names:
            matching=[k for k in names if name.casefold() in k.casefold()]
            assert len(matching)==1,(theme,name,matching)
            name=matching[0]
        p=names[name][1].centroid;anchors.append([x,y,p.x,p.y])
    if spec.get('lake_alignment'):
        lake=names[spec['lake_alignment']][1]
        before=Polygon(geo['features']['lakes'][0])
        def axes(points):
            pts=np.asarray(points);centre=pts.mean(axis=0);_,_,v=np.linalg.svd(pts-centre)
            a=v[0]
            if a[1]>0:a=-a
            b=np.array([-a[1],a[0]])
            radii=np.percentile(abs((pts-centre)@np.array([a,b]).T),98,axis=0)
            return centre,np.array([a,b]),radii
        oldc,olda,oldr=axes(before.exterior.coords)
        actual=[project(x,y) for x,y in lake.exterior.coords];newc,newa,newr=axes(actual)
        def convert(points):return ((np.asarray(points)-oldc)@olda.T*(newr/oldr))@newa+newc
        anchor_method='Principal axes and shore extent of actual OpenStreetMap Loch Ness polygon'
    else:
        # Every map has its own selected physical anchors. No common world grid
        # or random geographical placement is used.
        old=np.array([[x/ow,y/oh] for x,y,_,_ in anchors]);new=np.array([project(lon,lat) for _,_,lon,lat in anchors])
        if len(anchors)==3:
            coefficients=np.linalg.solve(np.column_stack([old,np.ones(3)]),new)
            def convert(points):
                a=np.asarray(points)/[ow,oh];return np.column_stack([a,np.ones(len(a))])@coefficients
        else:
            corners=np.array([[0,0],[1,0],[1,1],[0,1]])
            dest=corners*[width*.84,height*.84]+[width*.08,height*.08]
            mapping=RBFInterpolator(np.vstack([old,corners]),np.vstack([new,dest]),kernel='thin_plate_spline',smoothing=.004)
            def convert(points):return mapping(np.asarray(points)/[ow,oh])
        anchor_method='Individually selected WGS84 landscape anchors; smooth display-only interpolation'
    # Convert the primary geographic source directly; all shoreline and forest
    # vertices retain their original latitude/longitude provenance.
    from shapely.ops import transform
    def projected(g):
        return transform(lambda x,y,z=None:((np.asarray(x)-w)*cos(radians(latitude))*factor,(n-np.asarray(y))*factor),g).intersection(clip).simplify(2,preserve_topology=True)
    drawn=[];water=[];land=None
    coastline=[g for row,g in shapes if row.get('tags',{}).get('natural')=='coastline' and g.geom_type in ('LineString','Polygon')]
    if theme=='dingo':
        rings=list(polygonize(unary_union([g.exterior if g.geom_type=='Polygon' else g for g in coastline])))
        candidates=[g for g in rings if g.contains(Point(153.08,-25.45))]
        assert candidates,'K’gari coastline must form a true land polygon'
        land=projected(max(candidates,key=lambda g:g.area))
    for row,g in shapes:
        t=row.get('tags',{});kind=None
        if t.get('natural')=='water' or t.get('waterway')=='riverbank':kind='water'
        elif t.get('waterway') in ('river','stream','canal'):kind='river'
        elif t.get('natural') in ('wood','scrub') or t.get('landuse')=='forest':kind='forest'
        elif t.get('natural') in ('sand','bare_rock') or t.get('landuse') in ('farmland','meadow'):kind='terrain'
        elif t.get('landuse')=='residential':kind='settlement'
        elif t.get('boundary')=='national_park':kind='boundary'
        elif t.get('highway'):kind='reference-road'
        if not kind:continue
        pg=projected(g)
        if pg.is_empty:continue
        if kind in ('forest','terrain','settlement') and pg.area<width*height*.00006:continue
        if kind=='water' and pg.area>0:water.append(pg)
        drawn.append((kind,pg,t.get('name',''),row['id']))
    wet=unary_union(water)
    positions={};adjustments=[]
    # Small shore access adjustments are public cartographic placements, never
    # modifications to a game action, its cost, its task or its hidden ability.
    keys=sorted(public['locations'],key=lambda k:(public['locations'][k]['kind']=='junction',k))
    mapped=convert([[public['locations'][k]['x'],public['locations'][k]['y']] for k in keys])
    for k,(x,y) in zip(keys,mapped):
        p=Point(float(x),float(y));q=p
        if land is not None and not land.buffer(-12).covers(q):q=nearest_points(q,land.buffer(-16))[1]
        if not wet.is_empty and wet.buffer(12).contains(q):q=nearest_points(q,wet.buffer(18).boundary)[1]
        if not clip.buffer(-35).covers(q):q=nearest_points(q,clip.buffer(-40))[1]
        if any(hypot(q.x-v['x'],q.y-v['y'])<65 for v in positions.values()):
            found=None
            for radius in (70,100,140,190,240):
                for angle in np.linspace(0,2*np.pi,32,endpoint=False):
                    candidate=Point(q.x+radius*np.cos(angle),q.y+radius*np.sin(angle))
                    if not clip.buffer(-35).covers(candidate):continue
                    if land is not None and not land.buffer(-12).covers(candidate):continue
                    if not wet.is_empty and wet.buffer(12).contains(candidate):continue
                    if all(hypot(candidate.x-v['x'],candidate.y-v['y'])>=65 for v in positions.values()):
                        found=candidate;break
                if found is not None:break
            assert found is not None,(theme,k,'No distinct geographic access point')
            q=found
        positions[k]={'x':round(q.x,3),'y':round(q.y,3),'longitude':inverse(q.x,q.y)[0],'latitude':inverse(q.x,q.y)[1]}
        if q.distance(p)>.1:adjustments.append({'node':k,'distance_display_units':round(q.distance(p),2)})
    # Keep the existing graph's links and costs. Curves sample the same spatial
    # transform so the foreground follows the authored geographic placement.
    paths={}
    for a,b,_ in public['edges']:
        p=np.array([public['locations'][a]['x'],public['locations'][a]['y']]);q=np.array([public['locations'][b]['x'],public['locations'][b]['y']])
        line=convert([p+(q-p)*t for t in np.linspace(0,1,9)])
        line[0]=[positions[a]['x'],positions[a]['y']];line[-1]=[positions[b]['x'],positions[b]['y']]
        paths['|'.join(sorted((a,b)))]=[[round(x,3),round(y,3)] for x,y in line]
    root=ET.Element('{'+NS+'}svg',{'viewBox':f'0 0 {width} {height:.2f}','width':str(width),'height':f'{height:.2f}','data-cartography':'geographic-atlas-1'})
    def el(tag,attrs=None,text=None):
        item=ET.SubElement(root,'{'+NS+'}'+tag,{k:str(v) for k,v in (attrs or {}).items()});item.text=text;return item
    def path(g,attrs):
        def line(coords,closed=False):return 'M'+'L'.join(f'{x:.2f} {y:.2f}' for x,y in coords)+('Z' if closed else '')
        if g.geom_type=='Polygon':
            d=line(g.exterior.coords,True)+''.join(line(r.coords,True) for r in g.interiors);el('path',{'d':d,'fill-rule':'evenodd',**attrs})
        elif g.geom_type in ('LineString','LinearRing'):el('path',{'d':line(g.coords),'fill':'none',**attrs})
        elif hasattr(g,'geoms'):
            for part in g.geoms:path(part,attrs)
    el('title',text=MAPS[mid][0]+' · 真实地理底图')
    el('desc',text='OpenStreetMap WGS84 地理轮廓与地物。处理站、测点和实验连线由本项目设置，不是现实设施或道路导航。')
    el('rect',{'width':width,'height':height,'fill':'#a9c7ca' if land is not None else '#eee8d5'})
    if land is not None:path(land,{'fill':'#eee8d5','stroke':'#859a82','stroke-width':5})
    if theme=='forest':
        for row,g in shapes:
            if row.get('tags',{}).get('name')=='Muir Woods National Monument':
                path(projected(g),{'fill':'#b8c9aa','fill-opacity':.45,'stroke':'#859a82','stroke-width':3})
    if theme=='capulin':
        for row,g in shapes:
            if row.get('tags',{}).get('name')=='Crater Rim Trail':
                path(projected(g),{'fill':'#d5c29f','fill-opacity':.45,'stroke':'#859a82','stroke-width':3})
    order=['forest','terrain','settlement','reference-road','boundary','river','water']
    for kind in order:
        rows=[r for r in drawn if r[0]==kind]
        if kind in ('forest','terrain','settlement'):rows=sorted(rows,key=lambda r:r[1].area,reverse=True)[:500]
        for _,g,name,oid in rows:
            attrs={
              'forest':{'fill':'#b8c9aa','fill-opacity':.5,'stroke':'#f7f4e9','stroke-width':2},
              'terrain':{'fill':'#d5c29f','fill-opacity':.34,'stroke':'#f7f4e9','stroke-width':2},
              'settlement':{'fill':'#bd9971','fill-opacity':.28,'stroke':'#f7f4e9','stroke-width':2},
              'reference-road':{'fill':'none','stroke':'#b8b29c','stroke-width':1.5,'opacity':.28},
              'boundary':{'fill':'none','stroke':'#7d9678','stroke-width':4,'stroke-dasharray':'12 8','opacity':.7},
              'river':{'fill':'none','stroke':'#91b3b6','stroke-width':4 if g.length>height*.12 else 2,'opacity':.9},
              'water':{'fill':'#a9c7ca','stroke':'#839fa3','stroke-width':2.5},
            }[kind];path(g,attrs)
    # Geographic labels refer to source features, not abilities or target hints.
    labels=[]
    for row,g in shapes:
        t=row.get('tags',{});name=t.get('name');p=project(g.centroid.x,g.centroid.y)
        if not name or not clip.buffer(-100).contains(Point(*p)):continue
        if t.get('place') not in ('town','village') and t.get('natural') not in ('water','peak'):continue
        importance=g.area if g.area else .0001 if t.get('place') else .00001
        labels.append((importance,name,p,row))
    used=[]
    for _,name,p,row in sorted(labels,key=lambda v:-v[0]):
        if any(hypot(*(p-q))<480 for q in used):continue
        if len(used)>=12:break
        used.append(p);el('text',{'x':round(p[0],2),'y':round(p[1],2),'text-anchor':'middle','fill':'#4c6e63','font-family':'Microsoft YaHei,Noto Sans,sans-serif','font-size':31,'opacity':.65,'paint-order':'stroke','stroke':'#f7f4e9','stroke-width':5},name)
    el('rect',{'x':0,'y':height-74,'width':width,'height':74,'fill':'#f7f4e9','fill-opacity':.92})
    degree=lambda v,axis:f'{abs(v):.3f}°'+(('E' if v>=0 else 'W') if axis=='lon' else ('N' if v>=0 else 'S'))
    el('text',{'x':55,'y':height-28,'fill':'#48685d','font-family':'sans-serif','font-size':24},f'© OpenStreetMap contributors · WGS84 · {degree(w,"lon")}–{degree(e,"lon")} / {degree(s,"lat")}–{degree(n,"lat")}')
    el('text',{'x':width-55,'y':height-28,'text-anchor':'end','fill':'#48685d','font-family':'Microsoft YaHei,sans-serif','font-size':24},'地理底图 · 实验路网')
    ET.indent(root);svg=ET.tostring(root,encoding='unicode')+'\n'
    asset=public['terrain']+'-geographic.svg'
    (ROOT/'memorybenchmark/static'/asset).write_text(svg,encoding='utf-8')
    record={'schema':'human-geographic-presentation-1','map_id':mid,'terrain':public['terrain'],
      'source_geometry_sha256':digest({'locations':public['locations'],'edges':public['edges']}),
      'view_box':[0,0,width,round(height,3)],'positions':positions,'edge_paths':paths,'terrain_asset':'/'+asset,
      'reference':{'crs':'EPSG:4326','bbox':spec['bbox'],'source':'OpenStreetMap contributors','license':'ODbL 1.0',
        'url':'https://www.openstreetmap.org/copyright','retrieved_utc':source['utc'],'source_sha256':source['sha256'],
        'anchor_method':anchor_method,'anchors':anchors,'experimental_links_not_real_roads':True},
      'review':{'source_elements':len(elements),'drawn_features':len(drawn),'water_polygons':len(water),
        'source_labels':len(used),'shore_adjustments':adjustments,'game_tasks_changed':False,'game_graph_changed':False}}
    (OUT/(mid+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # Build a contact-sheet view of the actual geographic overlay.
    for a,b,_ in public['edges']:
        pts=paths['|'.join(sorted((a,b)))];el('path',{'d':'M'+'L'.join(f'{x} {y}' for x,y in pts),'fill':'none','stroke':'#657e62','stroke-width':5,'opacity':.7})
    for k,p in positions.items():
        node=public['locations'][k];x,y=p['x'],p['y'];r=15 if node['kind']=='station' else 10
        el('circle',{'cx':x,'cy':y,'r':r,'fill':'#f7f4e9','stroke':'#48685d','stroke-width':4})
    (S/(mid+'.svg')).write_text(ET.tostring(root,encoding='unicode'),encoding='utf-8')
    print(json.dumps({'map':mid,'nodes':len(positions),'drawn':len(drawn),'adjusted':len(adjustments),'svg_bytes':len(svg.encode())}),flush=True)
    return record

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,required=True,help='Directory of downloaded OpenStreetMap JSON and source receipts')
    parser.add_argument('--preview-dir',type=Path,default=S)
    parser.add_argument('--map',choices=tuple(SPECS))
    args=parser.parse_args();RAW=args.source_dir;S=args.preview_dir;S.mkdir(parents=True,exist_ok=True)
    for theme in ([args.map] if args.map else SPECS):make(theme)
