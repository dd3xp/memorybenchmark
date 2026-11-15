"""Geometry-only capability authoring for independently drawn Easy/Normal maps.

Every road and site comes from its own field_geography module. Existing public
builder entry points dispatch to v2; historical fixtures live under data/history.
No model responses, native memory or observed scores enter authoring.
"""
from collections import Counter
from heapq import heappop,heappush
import argparse,json
from pathlib import Path
from random import Random

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'memorybenchmark/data'


def geometry(design):
    p=design['public'];adj={s:[] for s in p['locations']}
    for a,b,w in p['edges']:adj[a].append((b,w));adj[b].append((a,w))
    distances={}
    for source in adj:
        queue=[(0,source)];seen={}
        while queue:
            cost,node=heappop(queue)
            if node in seen:continue
            seen[node]=cost
            for nxt,w in adj[node]:
                if nxt not in seen:heappush(queue,(cost+w,nxt))
        distances[source]=seen
    return distances


def fixture_diagnostics(design, fixture, distances=None):
    p=design['public'];d=distances or geometry(design);counts=Counter();near=0.;contexts=0;costs=[]
    station_type={s:t for t,v in p['station_types'].items() for s in v['stations']}
    assignment={s:([fixture[t]] if isinstance(fixture[t],str) else fixture[t]) for s,t in station_type.items()}
    for task in design['tasks'].values():
        for j,stage in enumerate(task['stages']):
            target=stage['target'];dest=task['stages'][j+1]['target'] if j+1<len(task['stages']) else task['submit_at'];kind=stage['required_kind']
            nearest=min(d[target][s] for s in assignment)
            nearest_stations=[s for s in assignment if d[target][s]==nearest]
            near+=sum(kind in assignment[s] for s in nearest_stations)/len(nearest_stations);contexts+=1
            valid=[s for s in assignment if kind in assignment[s]]
            best=min(d[target][s]+d[s][dest] for s in valid)
            winners=[s for s in valid if d[target][s]+d[s][dest]==best]
            if len(winners)==1:counts.update(winners)
            costs.append(best)
    return {'nearest_match_rate':near/contexts,'unused_strict_replicas':sorted(set(assignment)-set(counts)),
        'strict_replica_counts':dict(sorted(counts.items())),'stage_contexts':contexts,'mean_processing_leg_distance':sum(costs)/len(costs)}


def choose_fixture(design, *, normal, seed, trials):
    rng=Random(seed);kinds=list(design['public']['kinds']);types=list(design['public']['station_types']);d=geometry(design);best=None
    for _ in range(trials):
        if normal:
            slots=kinds*2;rng.shuffle(slots);labels=list(types);rng.shuffle(labels)
            parts=[slots[2*i:2*i+2] for i in range(8)]+[[x] for x in slots[16:]]
            if any(len(set(v))!=len(v) for v in parts):continue
            fixture={t:sorted(v) for t,v in zip(labels,parts)}
        else:
            order=list(kinds);rng.shuffle(order);fixture=dict(zip(types,order))
        stats=fixture_diagnostics(design,fixture,d)
        # Predeclared geometry criteria, never agent outcomes: all replicas should
        # be useful; geographically nearest guessing should remain near 1/8.
        score=(len(stats['unused_strict_replicas']),abs(stats['nearest_match_rate']-.125),stats['mean_processing_leg_distance'])
        if best is None or score<best[0]:best=(score,fixture,stats)
        if score[0]==0 and score[1]<.025:break
    if best is None:raise ValueError('No valid authored fixture')
    design['evaluation']['authoring_geometry_check']=dict(best[2],seed=seed,trials_limit=trials,
        method='Fixed-seed geometry-only candidate search; not calibrated against native agent outcomes.')
    return best[1]


def balance_task_locations(design, *, seed, fixture=None):
    """Keep material order/counts and five visits per target; balance usefulness."""
    rng=Random(seed); fixture=fixture or design['private_station_capabilities'];d=geometry(design)
    stages=[s for task in design['tasks'].values() for s in task['stages']]
    def score():
        r=fixture_diagnostics(design,fixture,d)
        repeated=sum(n-1 for n in Counter((s['target'],s['required_kind']) for s in stages).values() if n>1)
        return len(r['unused_strict_replicas'])*100+abs(r['nearest_match_rate']-.125)*30+repeated*.05,r
    value,stats=score();best=(value,[s['target'] for s in stages],stats)
    for step in range(24000):
        a,b=rng.sample(range(len(stages)),2)
        if a//2==b//2:continue
        stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
        if any(stages[i]['target']==stages[i+1]['target'] for i in (a//2*2,b//2*2)):
            stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target'];continue
        candidate,stats=score()
        # A short, deterministic annealing cycle escapes tied geometric layouts.
        temperature=10*(1-(step%2400)/2400)
        from math import exp
        accept=candidate<=value or rng.random()<exp(min(0,(value-candidate)/max(.1,temperature)))
        if accept:value=candidate
        else:stages[a]['target'],stages[b]['target']=stages[b]['target'],stages[a]['target']
        if accept and value<best[0]:best=(value,[s['target'] for s in stages],stats)
        if best[2]['unused_strict_replicas']==[] and abs(best[2]['nearest_match_rate']-.125)<.025:break
        if step%2400==2399:
            for stage,target in zip(stages,best[1]):stage['target']=target
            value=best[0]
    for stage,target in zip(stages,best[1]):stage['target']=target
    for task in design['tasks'].values():task['target']=task['stages'][0]['target']
    design['evaluation']['authoring_geometry_check']=dict(best[2],seed=seed,
        method='Geometry-only fixed-fixture and target-swap authoring; material order, requirements and target frequency preserved; no native agent outcomes.')


def forest_geo():
    from scripts.build_field_maps import build
    return build('forest')


def rainbow_easy():
    from scripts.build_field_maps import build
    return build('capulin')


def normal_map(theme):
    from scripts.build_field_maps import build
    return build({'nessie-normal':'nessie','dingo':'dingo','boar':'boar'}[theme])


def main():
    from scripts.build_field_maps import FILES,build
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map',choices=tuple(FILES),help='Prefer reviewing one map at a time')
    args=parser.parse_args()
    for theme in ([args.map] if args.map else FILES):
        design=build(theme);path=DATA/(FILES[theme]+'.json')
        path.write_text(json.dumps(design,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'map':theme,'version':design['design_id'],'nodes':len(design['public']['locations']),
            'roads':len(design['public']['edges']),'new_model_calls':0},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
