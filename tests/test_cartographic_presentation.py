"""Real-world human map layers must never replace the scientific game state."""
from copy import deepcopy
from itertools import combinations
from math import hypot
from pathlib import Path
import json
import tempfile

from memorybenchmark.cartography import geographic_presentation
from memorybenchmark.map_catalog import MAPS, map_detail, station_design
from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_capability import load_design


def test_nine_geographic_maps_match_graphs_and_have_distinct_access_points():
    for mid in MAPS:
        if mid.endswith('-lunatic'):
            continue
        design = load_design(station_design(mid))
        original = deepcopy(design)
        layer = geographic_presentation(design['public'])
        assert layer and design == original
        assert layer['cartographic_reference']['crs'] == 'EPSG:4326'
        assert layer['cartographic_reference']['source'] == 'OpenStreetMap contributors'
        assert set(layer['locations']) == set(design['public']['locations'])
        assert layer['edges'] == design['public']['edges']
        points = list(layer['locations'].values())
        assert min(hypot(a['x']-b['x'],a['y']-b['y']) for a,b in combinations(points,2)) >= 64.9
        for a,b,_ in layer['edges']:
            path = layer['edge_paths']['|'.join(sorted((a,b)))]
            for endpoint in (a,b):
                n = layer['locations'][endpoint]
                assert [n['x'],n['y']] in (path[0],path[-1])
        detail = map_detail(mid)
        assert detail['map']['locations'] == layer['locations']
        assert Path('memorybenchmark/static', layer['terrain_asset'].lstrip('/')).is_file()


def test_changed_graph_cannot_silently_reuse_geographic_coordinates():
    public = deepcopy(load_design(station_design('orcia-hard'))['public'])
    public['edges'][0][2] += 1
    assert geographic_presentation(public) is None


def test_human_presentation_does_not_modify_delivered_game_observation():
    design = load_design(station_design('capulin-easy'))
    with tempfile.TemporaryDirectory() as folder:
        service = FieldService(folder, design)
        result = service.start({})
        assert result['observation']['environment']['locations'] == design['public']['locations']
        assert result['presentation']['geographic_map']['locations'] != design['public']['locations']
        assert service.design == design
        events = Path(folder)/'station-human'/result['instance_id']/'events.jsonl'
        assert 'cartographic_reference' not in events.read_text(encoding='utf-8')


def test_geographic_assets_contain_source_attribution_and_no_capability_data():
    for p in Path('memorybenchmark/cartographic_maps').glob('*.json'):
        layer = json.loads(p.read_text(encoding='utf-8'))
        svg = Path('memorybenchmark/static', layer['terrain_asset'].lstrip('/')).read_text(encoding='utf-8')
        assert 'OpenStreetMap contributors' in svg and 'WGS84' in svg
        assert 'private_station_capabilities' not in svg
        assert 'private_worlds' not in svg
