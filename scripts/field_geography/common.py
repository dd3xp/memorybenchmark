"""Only drawing and graph primitives are shared; every site and road is authored."""
from random import Random
from scripts.hard_geography.common import Landscape
from scripts.hard_geography.review import review

EASY_SURVEYS='PQRSUVXY'
NORMAL_SURVEYS='PQRSUVXYZWTO'

def finish(g,seed,*,normal=False,replica_pairs=None):
    letters='ABCDEFGHIJKLMNOP' if normal else 'ABCDEFGH'
    surveys=NORMAL_SURVEYS if normal else EASY_SURVEYS
    geo=g.finish(seed,minimum_replica_distance=550 if normal else 460,
                 station_types=letters,survey_count=len(surveys))
    if replica_pairs:
        if sorted(i for pair in replica_pairs for i in pair)!=list(range(len(g.slots))):
            raise ValueError('Authored replica pairing must cover every physical site once')
        by_xy={(p['x'],p['y']):k for k,p in geo['locations'].items() if p['kind']=='station'}
        labels=list(letters);rng=Random(seed+200);rng.shuffle(labels);relabel={}
        for typ,pair in zip(labels,replica_pairs):
            replicas=[1,2];rng.shuffle(replicas)
            for index,replica in zip(pair,replicas):relabel[by_xy[g.xy(g.slots[index])]]=typ+str(replica)
        geo['locations']={relabel.get(k,k):v for k,v in geo['locations'].items()}
        for k,p in geo['locations'].items():
            if p['kind']=='station':p.update(name=k[0]+'型处理站·'+k,station_type=k[0])
        geo['edges']=[[relabel.get(a,a),relabel.get(b,b),w] for a,b,w in geo['edges']]
        geo['edge_tags']={'|'.join(sorted(relabel.get(n,n) for n in key.split('|'))):v for key,v in geo['edge_tags'].items()}
    rename=dict(zip(geo['surveys'],surveys))
    geo['locations']={rename.get(k,k):v for k,v in geo['locations'].items()}
    geo['edges']=[[rename.get(a,a),rename.get(b,b),w] for a,b,w in geo['edges']]
    geo['surveys']=list(surveys)
    geo['edge_tags']={'|'.join(sorted(rename.get(n,n) for n in key.split('|'))):v for key,v in geo['edge_tags'].items()}
    # Keep road names public, but station letters remain unrelated to geography.
    geo['geometry_review']=review(geo)
    return geo

def draw_bridges(d,geo):
    for a,b in geo['features'].get('bridges',[]):
        p,q=(geo['locations'][k] for k in (a,b))
        path=f'M{p["x"]},{p["y"]}L{q["x"]},{q["y"]}'
        d.path(path,stroke='#8d907a',width=25)
        d.path(path,stroke='#eee9d4',width=17)
