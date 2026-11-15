from scripts.hard_geography.common import Landscape
from scripts.hard_geography.review import review

def finish(g,seed):
    geo=g.finish(seed,minimum_replica_distance=1700)
    geo['geometry_review']=review(geo)
    r=geo['geometry_review']
    if r['unconnected_visual_crossings'] or r['unapproved_barrier_crossings']:raise ValueError(r)
    if r['minimum_point_separation']<85:raise ValueError(r)
    return geo
