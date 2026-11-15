"""Georeferenced whole-region graphs with public land-use destinations.

Natural Earth provides reference outlines/places. The experimental roads,
facilities, survey sites and region partitions are authored abstractions;
they do not reconstruct historical roads or historical species ranges.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
from itertools import combinations
from math import hypot,cos,sin
from pathlib import Path
import json
from scripts.hard_geography.common import intersection,topology
from scripts.hard_geography.review import inside,point_distance,enters_polygon

DATA=Path(__file__).with_name('whole_region_data')
REGION_NAMES={'natural':'自然区域','settlement':'人类聚居区','habitat':'动物栖息区'}
COLORS={'natural':'#7c9a75','settlement':'#bd9971','habitat':'#a192b4'}

def build(theme):return deepcopy(_build(theme))

@lru_cache(maxsize=3)
def _build(theme):
    raw=json.loads((DATA/(theme+'.json')).read_text(encoding='utf-8'))
    nodes=deepcopy(raw['locations']);w,h=raw['view_box'][2:]
    land=raw['land_polygons'];lakes=raw['lake_polygons'];context_land=raw['context_land_polygons']
    def xy(k):return nodes[k]['x'],nodes[k]['y']
    def walkable(p):return any(inside(p,ring) for ring in land) and not any(inside(p,ring) for ring in lakes)
    dry=lambda p:any(inside(p,ring) for ring in context_land) and not any(inside(p,ring) for ring in lakes)
    seeds={r['id']:{'id':r['id'],'category':r['category'],'x':r['x'],'y':r['y']} for r in raw['region_seeds']}
    for k,n in nodes.items():
        if n.get('source','').startswith('Natural Earth'):
            seeds[k]={'id':k,'category':'settlement','x':n['x'],'y':n['y']}
    seed_rows=list(seeds.values())
    def region(p):return min(seed_rows,key=lambda r:(hypot(p[0]-r['x'],p[1]-r['y']),r['id']))
    # Reference landmarks can designate lakes rather than shore access. Move
    # access points to the nearest separated shore position; retain originals.
    references={k:{field:n[field] for field in ('name','reference_coordinates','source') if field in n} for k,n in nodes.items()}
    changes=[];placed={}
    for k in sorted(nodes,key=lambda k:(nodes[k]['kind'] not in ('station','survey'),k)):
        n=nodes[k];original=xy(k);expected=n['region_category'] if n['kind'] in ('station','survey') else None
        def acceptable(p):
            return (50<p[0]<w-50 and 50<p[1]<h-50 and walkable(p)
                and (expected is None or region(p)['category']==expected)
                and all(hypot(p[0]-q[0],p[1]-q[1])>=90 for q in placed.values()))
        if not acceptable(original):
            found=None
            for radius in range(30,1531,30):
                for j in range(32):
                    p=(original[0]+radius*cos(j*2.3999632297),original[1]+radius*sin(j*2.3999632297))
                    if acceptable(p):found=p;break
                if found:break
            if found is None:raise ValueError((theme,k,'no separated shore/region access'))
            n['x'],n['y']=map(lambda value:round(value,4),found);changes.append({'node':k,'before':original,'after':xy(k)})
        placed[k]=xy(k)
    # Public regional identity always agrees with the drawn region partition.
    aliases={r['id']:'r'+str(i+1).zfill(3) for i,r in enumerate(seed_rows)}
    for k,n in nodes.items():
        r=region(xy(k));n['region_id']=aliases[r['id']];n['region_category']=r['category']
        n['name']=(f"{n['station_type']}型处理站·{k}" if n['kind']=='station' else
                   '巡测营地' if n['kind']=='camp' else f'测绘点·{k}' if n['kind']=='survey' else f'地区路口·{k}')
        for key in ('source','reference_coordinates'):n.pop(key,None)
    edges={}
    def mode(a,b):
        p,q=xy(a),xy(b)
        if not all(dry((p[0]+(q[0]-p[0])*i/24,p[1]+(q[1]-p[1])*i/24)) for i in range(1,24)):
            return 'ferry'
        # Check every boundary interval, not just a finite sample that can
        # miss a narrow fjord/lake. Foreign land is land, never a fake ferry.
        bounds=[0.,1.]
        for ring in context_land+lakes:
            if max(p[0],q[0])<min(x for x,y in ring) or min(p[0],q[0])>max(x for x,y in ring) or max(p[1],q[1])<min(y for x,y in ring) or min(p[1],q[1])>max(y for x,y in ring):continue
            for u,v in zip(ring,ring[1:]+ring[:1]):
                hit=intersection(p,q,u,v)
                if hit:bounds.append(max(0,min(1,hit[0])))
        bounds=sorted(set(bounds))
        return 'land' if all(dry((p[0]+(q[0]-p[0])*(a+b)/2,p[1]+(q[1]-p[1])*(a+b)/2)) for a,b in zip(bounds,bounds[1:])) else 'ferry'
    def add(a,b,kind=None):
        if a==b:return
        edges[tuple(sorted((a,b)))]=(max(1,round(hypot(xy(a)[0]-xy(b)[0],xy(a)[1]-xy(b)[1])/220)),kind or mode(a,b))
    core=[k for k,n in nodes.items() if n['kind'] not in ('station','survey')]
    for e in raw['edges']:
        if e['a'] in core and e['b'] in core:add(e['a'],e['b'])
    # Local alternatives follow the actual, different reference-place layouts.
    # Keep sea crossings explicit rather than silently drawing roads on water.
    candidates=[]
    for a in core:
        near=sorted((b for b in core if a!=b),key=lambda b:(hypot(xy(a)[0]-xy(b)[0],xy(a)[1]-xy(b)[1]),b))[:6]
        candidates.extend((hypot(xy(a)[0]-xy(b)[0],xy(a)[1]-xy(b)[1]),a,b) for b in near)
    for length,a,b in sorted(candidates):
        if tuple(sorted((a,b))) in edges or length>2000 or mode(a,b)!='land':continue
        if any(intersection(xy(a),xy(b),xy(c),xy(d)) for (c,d),(_,tag) in edges.items() if tag=='land' and not {a,b}&{c,d}):continue
        add(a,b,'land')
    for i,(k,n) in enumerate((item for item in nodes.items() if item[1]['kind'] in ('station','survey'))):
        nearest=sorted(core,key=lambda a:(hypot(xy(k)[0]-xy(a)[0],xy(k)[1]-xy(a)[1]),a))
        add(k,nearest[0])
        if n['kind']=='station' and i%2 and hypot(xy(k)[0]-xy(nearest[1])[0],xy(k)[1]-xy(nearest[1])[1])<750:
            add(k,nearest[1])
    # Every land/land intersection is an actual junction. Ferry lines join
    # their named ports only; their schematic crossings are not transfer ports.
    junctions={}
    for iteration in range(10000):
        crossing=None
        for (a,b),(c,d) in combinations(list(edges),2):
            if {a,b}&{c,d} or edges[(a,b)][1]!='land' or edges[(c,d)][1]!='land':continue
            found=intersection(xy(a),xy(b),xy(c),xy(d))
            if found and 1e-6<found[0]<1-1e-6 and 1e-6<found[1]<1-1e-6:
                crossing=(a,b,c,d,found[2]);break
        if crossing is None:break
        a,b,c,d,p=crossing
        near=sorted((hypot(p[0]-xy(k)[0],p[1]-xy(k)[1]),k) for k in nodes)
        if near[0][0]<90:
            key=near[0][1]
        else:
            key='j'+str(len(junctions)+1).zfill(3);junctions[key]=p;r=region(p)
            nodes[key]={'x':p[0],'y':p[1],'kind':'junction','name':'道路交汇·'+key,'region_id':aliases[r['id']],'region_category':r['category']}
        edges.pop(tuple(sorted((a,b))));edges.pop(tuple(sorted((c,d))))
        for endpoint in (a,b,c,d):add(endpoint,key)
    else:raise ValueError((theme,'intersection normalization did not converge'))
    final={edge:value[0] for edge,value in edges.items()}
    tags={'|'.join(edge):[value[1]] for edge,value in edges.items()}
    used={k for edge in final for k in edge}
    nodes={k:n for k,n in nodes.items() if k in used}
    roads=[[a,b,weight] for (a,b),weight in final.items()]
    review_crossings=[]
    for (a,b),(c,d) in combinations(final,2):
        if {a,b}&{c,d} or tags['|'.join((a,b))]!=['land'] or tags['|'.join((c,d))]!=['land']:continue
        if intersection(xy(a),xy(b),xy(c),xy(d)):review_crossings.append([a,b,c,d])
    minimum=min(hypot(a['x']-b['x'],a['y']-b['y']) for a,b in combinations(nodes.values(),2))
    regions=[{'id':aliases[r['id']],'category':r['category'],'name':REGION_NAMES[r['category']]+'·'+aliases[r['id']],
              'x':r['x'],'y':r['y'],'polygon':next(c['polygon'] for c in raw['region_cells'] if c['id']==r['id']) if any(c['id']==r['id'] for c in raw['region_cells']) else []} for r in seed_rows]
    # Recompute cells after adding settlement seeds, so colors and legality
    # cannot disagree even near a regional border.
    for r,seed in zip(regions,seed_rows):
        poly=[(0,0),(w,0),(w,h),(0,h)];sx,sy=seed['x'],seed['y']
        for other in seed_rows:
            if other is seed:continue
            ox,oy=other['x'],other['y'];aa,bb=2*(ox-sx),2*(oy-sy);cc=ox*ox+oy*oy-sx*sx-sy*sy;out=[]
            for p,q in zip(poly,poly[1:]+poly[:1]):
                f=aa*p[0]+bb*p[1]-cc;g=aa*q[0]+bb*q[1]-cc
                if f<=1e-6:out.append(p)
                if (f<0)!=(g<0):
                    t=f/(f-g);out.append((p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])))
            poly=out
            if not poly:break
        r['polygon']=poly
    stats=topology(nodes,roads)
    if not stats['connected'] or len(nodes)<200 or review_crossings:raise ValueError((theme,stats,review_crossings))
    if minimum<50:raise ValueError((theme,'markers too close',minimum))
    return {'locations':nodes,'edges':roads,'view_box':raw['view_box'],'surveys':sorted(k for k,n in nodes.items() if n['kind']=='survey'),
        'regions':regions,'features':{'land':land,'context_land':raw['context_land_polygons'],'lakes':lakes},
        'topology':stats,'edge_tags':tags,'planar_junctions_added':len(junctions),'reference_locations':references,
        'source_data':raw['source_data'],'reference_bbox':raw['reference_bbox'],'access_adjustments':changes,
        'geometry_review':{'unconnected_visual_crossings':review_crossings,'unapproved_barrier_crossings':[],
            'minimum_point_separation':round(minimum,2),'explicit_ferry_connections':sum(v==['ferry'] for v in tags.values()),'topology':stats},
        'rationale':[raw['scope'],raw['spatial_note'],'Whole-region georeferenced layout; connectivity is an experimental abstraction, not historical-road reconstruction.',
                     'All 24 station types have one replica in each of the three publicly drawn processing-region categories.']}
