"""GPU geography is bounded display data, independently cullable and cacheable."""
from pathlib import Path
from hashlib import sha256
import gzip,json
from shapely.geometry import shape,Point
from memorybenchmark.web_assets import WEB_ASSETS
from scripts.build_world_gpu import geometries
import xml.etree.ElementTree as ET

STATIC=Path(__file__).resolve().parents[1]/'memorybenchmark/static'

def test_generated_gpu_sources_have_hashed_urls_and_exact_compressed_copies():
    manifest=json.loads((STATIC/'world-gpu.json').read_bytes())
    assert manifest['protocol']=='human-atlas-gpu-1' and len(manifest['regions'])==12
    records=[manifest['overview'],manifest['coast'],manifest['physical']]+[v for r in manifest['regions'].values() for v in r.values()]
    assert len(records)==24
    for record in records:
        data=(STATIC/record['url'].lstrip('/')).read_bytes()
        assert sha256(data).hexdigest()==record['sha256']
        assert record['sha256'][:16] in record['url'] and record['url'] in WEB_ASSETS
        assert gzip.decompress((STATIC/(record['url'].lstrip('/')+'.gz')).read_bytes())==data
        geo=json.loads(data);assert len(geo['features'])==record['features']
        assert all(f['geometry']['type'] in ('Polygon','LineString') for f in geo['features'])
        assert all(0<=f['properties']['opacity']<=1 for f in geo['features'])

def test_whole_kgari_is_preserved_in_gpu_overview_and_fine_coast():
    manifest=json.loads((STATIC/'world-gpu.json').read_bytes())
    for key in ('overview','coast'):
        geo=json.loads((STATIC/manifest[key]['url'].lstrip('/')).read_bytes())
        island=[shape(f['geometry']) for f in geo['features'] if f['properties']['kind']=='kgari-coastline']
        assert any(g.covers(Point(153.08,-25.45)) and g.bounds[3]-g.bounds[1]>.8 for g in island)

def test_disconnected_polygons_are_not_mistaken_for_holes_in_either_winding():
    for path in ('M0 0L0 10L10 10L10 0ZM20 0L20 10L30 10L30 0Z','M0 0L10 0L10 10L0 10ZM20 0L30 0L30 10L20 10Z'):
        parts=list(geometries(ET.fromstring('<path d="'+path+'"/>')))
        assert len(parts)==2 and all(g.area==100 for g in parts)
