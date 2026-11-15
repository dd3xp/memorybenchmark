"""Small cartographic tools. All settlements, routes and site positions are authored.

No common district template, force layout or random geography is used. Geometric
crossings are real graph junctions. Randomness only assigns anonymous station
type labels to already designed sites, independently of processing capabilities.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from math import hypot
from random import Random


def intersection(a,b,c,d):
    vx,vy=b[0]-a[0],b[1]-a[1];wx,wy=d[0]-c[0],d[1]-c[1]
    den=vx*wy-vy*wx
    if abs(den)<1e-8:return None
    dx,dy=c[0]-a[0],c[1]-a[1]
    t=(dx*wy-dy*wx)/den;u=(dx*vy-dy*vx)/den
    if -1e-8<=t<=1+1e-8 and -1e-8<=u<=1+1e-8:
        return t,u,(round(a[0]+t*vx,4),round(a[1]+t*vy,4))
    return None


def topology(locations,edges):
    adj={n:set() for n in locations}
    for a,b,_ in edges:adj[a].add(b);adj[b].add(a)
    reached=set();todo=[next(iter(adj))]
    while todo:
        node=todo.pop()
        if node in reached:continue
        reached.add(node);todo.extend(adj[node]-reached)
    # Strip service spurs, then contract degree-two road points. These describe
    # actual route structure rather than how many bends an illustrator drew.
    core={n:set(v) for n,v in adj.items()}
    while True:
        leaves=[n for n,v in core.items() if len(v)<2]
        if not leaves:break
        for n in leaves:
            for v in core[n]:core[v].discard(n)
            del core[n]
    degrees=Counter(len(v) for v in core.values() if len(v)!=2)
    return {'connected':len(reached)==len(adj),'nodes':len(adj),'roads':len(edges),
            'cycle_rank':len(edges)-len(adj)+1,
            'core_branch_degree_histogram':dict(sorted(degrees.items())),
            'station_degree_histogram':dict(sorted(Counter(len(adj[n]) for n,v in locations.items() if v['kind']=='station').items())),
            'dead_end_count':sum(len(v)==1 for v in adj.values())}


class Landscape:
    def __init__(self,theme,width,height,*,distance_unit=95):
        self.theme=theme;self.view_box=[0,0,width,height];self.distance_unit=distance_unit
        self.locations={};self.segments=[];self.routes=[];self.surveys=[];self.slots=[]
        self.regions=[];self.features={};self.rationale=[]

    def point(self,key,x,y,name,kind='junction',**extra):
        if key in self.locations:raise ValueError('Duplicate location '+key)
        if any(hypot(x-v['x'],y-v['y'])<1e-4 for v in self.locations.values()):raise ValueError('Coincident locations '+key)
        self.locations[key]={'name':name,'kind':kind,'x':x,'y':y,**extra};return key

    def xy(self,key):
        p=self.locations[key];return p['x'],p['y']

    def route(self,name,*points,tag='road',factor=1):
        path=[]
        for point in points:
            if isinstance(point,str):
                if point not in self.locations:raise ValueError('Unknown endpoint '+point)
                path.append(point)
            else:
                key=f'w{len(self.locations):03d}'
                path.append(self.point(key,*point,name+'转弯',transit=True))
        rid=len(self.routes)
        self.routes.append({'name':name,'path':path,'tag':tag})
        for a,b in zip(path,path[1:]):self.segments.append((a,b,rid,factor))

    def survey(self,x,y,name,*attachments):
        key=f'v{len(self.surveys)+1:02d}';self.point(key,x,y,name,'survey');self.surveys.append(key)
        for a in attachments:self.route(name+'小路',a,key)
        return key

    def station(self,x,y,*attachments):
        key=f'site{len(self.slots)+1:02d}';self.point(key,x,y,'待分配站址','station');self.slots.append(key)
        for a in attachments:self.route('站址通路',a,key)
        return key

    def finish(self,seed,*,minimum_replica_distance=850,station_types='ABCDEFGHIJKLMNOPQRSTUVWX',survey_count=16):
        if len(self.slots)!=2*len(station_types) or len(self.surveys)!=survey_count:
            raise ValueError(f'Expected {2*len(station_types)} stations and {survey_count} survey sites')
        points={tuple(round(x,4) for x in self.xy(k)):k for k in self.locations}
        splits=[{0:a,1:b} for a,b,_,_ in self.segments];created=[]
        for i,(a,b,_,_) in enumerate(self.segments):
            for j in range(i):
                c,d,_,_=self.segments[j]
                found=intersection(self.xy(a),self.xy(b),self.xy(c),self.xy(d))
                if not found:continue
                t,u,xy=found
                if t<1e-7:key=a
                elif t>1-1e-7:key=b
                elif u<1e-7:key=c
                elif u>1-1e-7:key=d
                elif xy in points:key=points[xy]
                else:
                    key=f'j{len(created)+1:02d}'
                    self.point(key,*xy,'田路交汇');points[xy]=key;created.append(key)
                splits[i][max(0,min(1,t))]=key;splits[j][max(0,min(1,u))]=key
        edges={};edge_tags=defaultdict(set)
        for (a,b,rid,factor),parts in zip(self.segments,splits):
            chain=[key for _,key in sorted(parts.items())]
            for u,v in zip(chain,chain[1:]):
                if u==v:continue
                key=tuple(sorted((u,v)))
                weight=max(1,round(hypot(self.xy(u)[0]-self.xy(v)[0],self.xy(u)[1]-self.xy(v)[1])/self.distance_unit*factor))
                edges[key]=min(weight,edges.get(key,weight));edge_tags[key].add(self.routes[rid]['tag'])
        rng=Random(seed);labels=[t+str(replica) for replica in (1,2) for t in station_types]
        for attempt in range(10000):
            rng.shuffle(labels);assignment=dict(zip(labels,self.slots))
            if all(hypot(self.xy(assignment[t+'1'])[0]-self.xy(assignment[t+'2'])[0],
                         self.xy(assignment[t+'1'])[1]-self.xy(assignment[t+'2'])[1])>minimum_replica_distance for t in station_types):break
        else:raise ValueError('Could not separate anonymous same-type replicas')
        rename=dict(zip(self.slots,labels))
        locations={rename.get(k,k):deepcopy(v) for k,v in self.locations.items()}
        for key,p in locations.items():
            if p['kind']=='station':p.update(name=key[0]+'型处理站·'+key,station_type=key[0])
        roads=[[rename.get(a,a),rename.get(b,b),w] for (a,b),w in edges.items()]
        degrees=Counter(n for edge in roads for n in edge[:2])
        for key,p in locations.items():
            if p.get('transit') and degrees[key]!=2:p.pop('transit')
        stats=topology(locations,roads)
        if not stats['connected']:raise ValueError('Disconnected authored landscape')
        return {'locations':locations,'edges':roads,'surveys':self.surveys,'view_box':self.view_box,
                'regions':self.regions,'features':self.features,'rationale':self.rationale,
                'topology':stats,'planar_junctions_added':len(created),
                'edge_tags':{'|'.join(sorted((rename.get(a,a),rename.get(b,b)))):sorted(tags) for (a,b),tags in edge_tags.items()}}
