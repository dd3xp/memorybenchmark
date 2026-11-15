"""Pure-Python geometric checks for the rendered, individually authored maps."""
from itertools import combinations
from math import hypot
from .common import intersection


def sampled_curve(points,subdivisions=20):
    p=[points[0],*points,points[-1]];result=[points[0]]
    for i in range(1,len(p)-2):
        a,b,c,d=p[i-1:i+3]
        u=(b[0]+(c[0]-a[0])/6,b[1]+(c[1]-a[1])/6)
        v=(c[0]-(d[0]-b[0])/6,c[1]-(d[1]-b[1])/6)
        for j in range(1,subdivisions+1):
            t=j/subdivisions;s=1-t
            result.append((s**3*b[0]+3*s*s*t*u[0]+3*s*t*t*v[0]+t**3*c[0],
                           s**3*b[1]+3*s*s*t*u[1]+3*s*t*t*v[1]+t**3*c[1]))
    return result


def point_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)


def segment_distance(a,b,c,d):
    if intersection(a,b,c,d):return 0
    return min(point_distance(a,c,d),point_distance(b,c,d),point_distance(c,a,b),point_distance(d,a,b))


def inside(point,polygon):
    x,y=point;answer=False
    for i,(a,b) in enumerate(polygon):
        c,d=polygon[i-1]
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:answer=not answer
    return answer


def enters_polygon(a,b,polygon):
    if inside(a,polygon) or inside(b,polygon):return True
    for c,d in zip(polygon,polygon[1:]+polygon[:1]):
        result=intersection(a,b,c,d)
        if result and 1e-6<result[0]<1-1e-6:return True
    return False


def review(geo):
    loc=geo['locations'];edges=geo['edges'];xy=lambda key:(loc[key]['x'],loc[key]['y'])
    crossings=[];barriers=[]
    for (a,b,_),(c,d,_) in combinations(edges,2):
        if {a,b}&{c,d}:continue
        found=intersection(xy(a),xy(b),xy(c),xy(d))
        if found:crossings.append([a,b,c,d])
    rivers=[(sampled_curve(r['points']),r['width']) for r in geo['features'].get('major_water',[])]
    for a,b,_ in edges:
        tags=set(geo['edge_tags']['|'.join(sorted((a,b)))])
        crossing_allowed=bool(tags&{'bridge','causeway'})
        if not crossing_allowed:
            for river,width in rivers:
                if any(segment_distance(xy(a),xy(b),c,d)<width/2-.5 for c,d in zip(river,river[1:])):
                    barriers.append({'edge':[a,b],'barrier':'river'})
            for polygon in geo['features'].get('lakes',[])+geo['features'].get('water_barriers',[]):
                if enters_polygon(xy(a),xy(b),polygon):barriers.append({'edge':[a,b],'barrier':'water body'})
        for polygon in geo['features'].get('rocks',[]):
            if enters_polygon(xy(a),xy(b),polygon):barriers.append({'edge':[a,b],'barrier':'rock mass'})
    stations=[key for key,n in loc.items() if n['kind']=='station']
    minimum=min(hypot(xy(a)[0]-xy(b)[0],xy(a)[1]-xy(b)[1]) for a,b in combinations(stations,2))
    point_minimum=min(hypot(xy(a)[0]-xy(b)[0],xy(a)[1]-xy(b)[1]) for a,b in combinations(loc,2))
    return {'unconnected_visual_crossings':crossings,'unapproved_barrier_crossings':barriers,
            'minimum_station_separation':round(minimum,2),'minimum_point_separation':round(point_minimum,2),
            'topology':geo['topology']}
