"""Human-facing geographic presentation, separate from native game observations."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import math

DATA = Path(__file__).with_name('cartographic_maps')


def _signature(public):
    value = {'locations': public['locations'], 'edges': public['edges']}
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             ensure_ascii=True).encode()).hexdigest()


@lru_cache(maxsize=16)
def _load(terrain):
    for path in sorted(DATA.glob('*.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['terrain'] == terrain:
            return record
    return None


def geographic_presentation(public):
    """Return a matched display layer without mutating the scientific map."""
    record = _load(public.get('terrain'))
    if record is None or record['source_geometry_sha256'] != _signature(public):
        return None
    assert set(record['positions']) == set(public['locations'])
    return {
        'locations': {key: {**deepcopy(node), **record['positions'][key]}
                      for key, node in public['locations'].items()},
        'edges': deepcopy(public['edges']),
        'view_box': deepcopy(record['view_box']),
        'edge_paths': deepcopy(record['edge_paths']),
        'terrain_asset': record['terrain_asset'],
        'cartographic_reference': deepcopy(record['reference']),
    }


@lru_cache(maxsize=1)
def _world_regions():
    path = Path(__file__).with_name('static') / 'world-atlas.json'
    return json.loads(path.read_text(encoding='utf-8'))['regions']


def world_presentation(public, geographic_bounds=None):
    """Project this run's public graph, never substitute a newer experiment graph."""
    region = next((r for r in _world_regions()
                   if r['terrain_asset'] == '/' + public.get('terrain', '') + '-world.svg'), None)
    if region is None:
        return None
    layer = geographic_presentation(public)
    local = {**public, **(layer or {})}
    bounds = layer['cartographic_reference']['bbox'] if layer else geographic_bounds
    if bounds is None:
        bounds = region['geographic_bounds']
    west, south, east, north = bounds
    x, y, width, height = local.get('view_box', [0, 0, 1200, 900])

    def project(a, b):
        lon = west + (a-x)/width*(east-west)
        lat = max(-85.05112878, min(85.05112878, north-(b-y)/height*(north-south)))
        return [(lon+180)*1000, (180-math.degrees(math.log(math.tan(math.pi/4+math.radians(lat)/2))))*1000]

    locations = {}
    for key, node in local['locations'].items():
        a, b = project(node['x'], node['y'])
        locations[key] = {**deepcopy(node), 'x': a, 'y': b}
    paths = {}
    for a, b, _ in public['edges']:
        key = '|'.join(sorted((a, b)))
        points = local.get('edge_paths', {}).get(key, [
            [local['locations'][a]['x'], local['locations'][a]['y']],
            [local['locations'][b]['x'], local['locations'][b]['y']]])
        dense = []
        for index, point in enumerate(points):
            if index:
                prior = points[index-1]
                pieces = max(1, min(80, int(abs(point[1]-prior[1])/180)+1))
                dense.extend(project(prior[0]+(point[0]-prior[0])*j/pieces,
                                     prior[1]+(point[1]-prior[1])*j/pieces) for j in range(1, pieces))
            dense.append(project(*point))
        paths[key] = dense
    top_left, bottom_right = project(x, y), project(x+width, y+height)
    return {'region_id': region['id'], 'projection': 'world-atlas-1',
            'view_box': [*top_left, bottom_right[0]-top_left[0], bottom_right[1]-top_left[1]],
            'locations': locations, 'edges': deepcopy(public['edges']), 'edge_paths': paths,
            'ferry_edges': deepcopy(public.get('ferry_edges', [])),
            'processing_regions': deepcopy(public.get('processing_regions', {}))}
