"""Check three fixed Easy maps and export actual scripted engine traces."""
from collections import Counter
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from itertools import product

from memorybenchmark.prototypes.station_capability import StationGame, load_design, map_world
from memorybenchmark.prototypes.station_routes import known_world_route, shortest_route
from memorybenchmark.prototypes.station_session import StationSession
from scripts.check_easy20_linked import FeedbackSimulation
from scripts.check_station_capability import trace_graph, render_svg
from scripts.build_easy_maps import DESIGN_PATHS


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ('nessie', 'loch ness', '尼斯湖', 'muir', '缪尔', 'plitvi', '普利特维采',
             'redwood creek', 'private_worlds', 'fixed_world', 'provenance', 'https://', 'http://')


def replica_choices(design):
    """Count all distance-optimal endpoints, keeping ties separate from preference."""
    assignment = design['private_worlds'][map_world(design)]
    any_optimal, strictly_preferred = Counter(), Counter()
    for task in design['tasks'].values():
        choices = [[s for s, kind in assignment.items() if kind == stage['required_kind']] for stage in task['stages']]
        options = []
        for stations in product(*choices):
            position = task['start']; cost = 0
            for stage, station in zip(task['stages'], stations):
                cost += shortest_route(design, position, stage['target'])[1] + shortest_route(design, stage['target'], station)[1]
                position = station
            options.append((cost + shortest_route(design, position, task['submit_at'])[1], stations))
        best = min(cost for cost, _ in options)
        for index in range(len(task['stages'])):
            endpoints = {stations[index] for cost, stations in options if cost == best}
            any_optimal.update(endpoints)
            if len(endpoints) == 1: strictly_preferred.update(endpoints)
    return {t: {s: {'optimal_including_ties': any_optimal[s], 'strictly_preferred': strictly_preferred[s]}
                 for s in group['stations']} for t, group in design['public']['station_types'].items()}


def topology(design):
    public = design['public']
    core = {k for k, n in public['locations'].items() if n['kind'] in ('camp', 'junction') and not n.get('transit')}
    edges = [(a, b) for a, b, _ in public['edges'] if a in core and b in core]
    links = {k: set() for k in core}
    for a, b in edges: links[a].add(b); links[b].add(a)
    cuts = []
    for removed in sorted(core):
        reached = set(); queue = [next(k for k in core if k != removed)]
        while queue:
            node = queue.pop()
            if node in reached: continue
            reached.add(node); queue.extend(links[node] - reached - {removed})
        if len(reached) < len(core)-1: cuts.append(removed)
    return {'core_nodes': len(core), 'core_edges': len(edges), 'independent_cycles': len(edges)-len(core)+1,
            'core_articulation_nodes': cuts,
            'total_nodes': len(public['locations']), 'total_roads': len(public['edges'])}


def check_map(name, output):
    path = DESIGN_PATHS[name]
    design = load_design(path); world = map_world(design); assignment = design['private_worlds'][world]
    output.mkdir(parents=True, exist_ok=False); (output/'graphs').mkdir()
    encoded = json.dumps(StationSession(StationGame(world, design), 'T1').initial, ensure_ascii=False).lower()
    assert not any(word in encoded for word in FORBIDDEN)
    assert len(design['material_selection']['common']) == 6 and len(design['material_selection']['special']) == 2
    assert 'capability_groups' not in design['public'] and len(design['private_worlds']) == 40320
    fixture = {}; ideal_replicas = Counter()
    for task_id in design['tasks']:
        ideal_replicas.update(known_world_route(design, task_id, assignment)['stations'])
    sim = FeedbackSimulation(design)
    for retain in (True, False):
        game = StationGame(world, design); facts = {}; rows = []
        for task in design['tasks']:
            row, new = sim.run(world, task, facts if retain else {}, runtime=game)
            if retain: facts = new
            graph = trace_graph(game)
            assert game.state.success and graph['distance'] == row['distance']
            assert len(graph['edges']) == row['moves']
            assert sum(e['action']['type'] == 'survey' for e in graph['node_events']) == 2
            assert graph['node_events'][-1]['action']['type'] == 'submit'
            label = 'retain' if retain else 'clear'
            data = json.dumps(graph, ensure_ascii=False, separators=(',', ':')).encode()
            (output/'graphs'/f'{label}-{task}.json.gz').write_bytes(gzip.compress(data, mtime=0))
            if task in ('T9', 'T13'):
                (output/f'{label}-{task}.svg').write_text(render_svg(design, graph, f'{design["public"]["name"]} {task} / scripted {label}'), encoding='utf-8')
            rows.append({'task': task, **row})
        raw = ''.join(json.dumps(e, ensure_ascii=False, separators=(',', ':'))+'\n' for e in game.events).encode()
        (output/f'{label}-events.jsonl.gz').write_bytes(gzip.compress(raw, mtime=0))
        fixture[label] = {'completed': sum(1 for _ in rows), 'rows': rows,
            'max_operations': max(r['operations'] for r in rows),
            'totals': {k: sum(r[k] for r in rows) for k in ('distance', 'operations', 'moves', 'station_attempts')},
            'followup_T2_T20': {k: sum(r[k] for r in rows[1:]) for k in ('distance', 'operations', 'moves', 'station_attempts')},
            'first_submission_correct_stages': sum(assignment[s['stations'][0]] == design['tasks'][row['task']]['stages'][i]['required_kind']
                                                    for row in rows for i, s in enumerate(row['decisions']))}
    pairs = [{'task': a['task'], 'retain_distance': a['distance'], 'clear_distance': b['distance'],
              'saved_distance': b['distance']-a['distance']} for a, b in zip(fixture['retain']['rows'], fixture['clear']['rows'])]
    assert fixture['retain']['rows'][0] == fixture['clear']['rows'][0]
    report = {'kind': 'scripted_map_check_not_native_agent_results', 'new_model_calls': 0,
        'design_id': design['design_id'], 'public_version': design['public']['version'],
        'configuration_sha256': sha256(path.read_bytes()).hexdigest(), 'topology': topology(design),
        'materials': design['material_selection'], 'candidate_assignments': len(design['private_worlds']),
        'fixed_fixture': fixture, 'task_distance_pairs': pairs,
        'known_route_replica_counts': {t: {s: ideal_replicas[s] for s in data['stations']} for t, data in design['public']['station_types'].items()},
        'replica_choices': replica_choices(design),
        'scope': 'One authored map, identical feedback-based script with retained or cleared actual experience. No externally written native memories. No guarantee that arbitrary wandering fits the budget or that native agents will realize these gains.'}
    (output/'validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    reports = []
    for key in ('nessie', 'forest', 'cascade'):
        report = check_map(key, args.output/key); reports.append(report)
        print(json.dumps({'map': key, 'topology': report['topology'],
            'results': {m: {'max_ops': r['max_operations'], **r['totals']} for m, r in report['fixed_fixture'].items()},
            'known_route_replica_counts': report['known_route_replica_counts'], 'model_calls': 0}, ensure_ascii=False), flush=True)
    (args.output/'summary.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__': main()
