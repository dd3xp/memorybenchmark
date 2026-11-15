"""Human world projection keeps each experiment's own immutable public graph."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from memorybenchmark.cartography import world_presentation
from memorybenchmark.map_catalog import MAPS, station_design


class ObserverWorldMapTests(unittest.TestCase):
    def test_all_current_graphs_align_with_catalog_without_mutating_public_state(self):
        static = Path(__file__).resolve().parents[1] / 'memorybenchmark/static'
        regions = {r['id']: r for r in json.loads((static/'world-atlas.json').read_text(encoding='utf-8'))['regions']}
        for mid in MAPS:
            with self.subTest(map=mid):
                design = json.loads(station_design(mid).read_text(encoding='utf-8'))
                original = deepcopy(design['public'])
                bounds = design.get('provenance', {}).get('reference_window', {}).get('bbox_west_south_east_north')
                display = world_presentation(design['public'], bounds)
                self.assertEqual(display['region_id'], mid)
                self.assertEqual(display['edges'], original['edges'])
                self.assertEqual(set(display['locations']), set(original['locations']))
                for key, node in display['locations'].items():
                    reference = regions[mid]['map']['locations'][key]
                    self.assertAlmostEqual(node['x'], reference['x'], places=5)
                    self.assertAlmostEqual(node['y'], reference['y'], places=5)
                self.assertEqual(design['public'], original)
                self.assertNotIn('capabilities', display)

    def test_historical_graph_and_own_reference_window_are_preserved(self):
        design = json.loads(station_design('scandinavia-lunatic').read_text(encoding='utf-8'))
        public = deepcopy(design['public'])
        removed = next(key for key, node in public['locations'].items() if node['kind'] == 'station')
        del public['locations'][removed]
        public['edges'] = [e for e in public['edges'] if removed not in e[:2]]
        public['edges'][0][2] += 7
        key = next(iter(public['locations']))
        public['locations'][key]['name'] = 'Historical public location'
        original = deepcopy(public)
        display = world_presentation(public, [10, 60, 12, 61])
        self.assertEqual(set(display['locations']), set(public['locations']))
        self.assertEqual(display['edges'], public['edges'])
        self.assertEqual(display['locations'][key]['name'], 'Historical public location')
        self.assertAlmostEqual(display['view_box'][0], 190000)
        self.assertAlmostEqual(display['view_box'][2], 2000)
        self.assertEqual(public, original)

    def test_unrecognized_historical_terrain_uses_existing_diagram(self):
        self.assertIsNone(world_presentation({'terrain':'legacy-fixture','locations':{},'edges':[]}))


if __name__ == '__main__':
    unittest.main()
