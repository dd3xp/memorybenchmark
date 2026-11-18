"""Human map browser: allowlisted geography, never agent task configuration."""

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
from .cartography import geographic_presentation

DATA = Path(__file__).parent / "data"
CURRENT_MAP = "capulin-easy"
MAPS = {
    "capulin-easy": ("卡普林火山", "Easy 01", "capulin_easy16.json"),
    "forest-easy": ("缪尔森林", "Easy 02", "forest_geo_easy16.json"),
    "cascade-easy": ("普利维特采湖区", "Easy 03", "cascade_easy16.json"),
    "nessie-normal": ("尼斯湖水怪", "Normal 01", "nessie_normal24.json"),
    "dingo-normal": ("澳洲野犬", "Normal 02", "dingo_normal24.json"),
    "boar-normal": ("野猪林", "Normal 03", "boar_normal24.json"),
    "orcia-hard": ("奥尔恰谷", "Hard 01", "orcia_hard36.json"),
    "hampi-hard": ("亨比", "Hard 02", "hampi_hard36.json"),
    "angkor-hard": ("吴哥", "Hard 03", "angkor_hard36.json"),
    "scandinavia-lunatic": (
        "斯堪的纳维亚",
        "Lunatic 01",
        "scandinavia_lunatic_recall64.json",
    ),
    "mongolia-lunatic": ("蒙古", "Lunatic 02", "mongolia_lunatic_recall64.json"),
    "andes-lunatic": ("安第斯", "Lunatic 03", "andes_lunatic_recall64.json"),
}


def station_design(map_id):
    if map_id not in MAPS:
        raise ValueError("地图不存在。")
    path = DATA / MAPS[map_id][2]
    if not path.is_file():
        raise ValueError("地图资源未安装。")
    return path


@lru_cache(maxsize=16)
def _detail(map_id):
    if map_id not in MAPS:
        raise ValueError("地图不存在。")
    name, variant, filename = MAPS[map_id]
    design = json.loads(station_design(map_id).read_text(encoding="utf-8"))
    public = design["public"]
    locations, edges = public["locations"], public["edges"]
    terrain = public.get("terrain", "field")
    triggers = [key for key, node in locations.items() if node.get("kind") == "station"]
    bounds = public.get("view_box")
    geographic = geographic_presentation(public)
    task_count = len(design["tasks"])
    if bounds is None:
        xs = [node["x"] for node in locations.values()]
        ys = [node["y"] for node in locations.values()]
        bounds = [
            min(xs) - 80,
            min(ys) - 80,
            max(xs) - min(xs) + 160,
            max(ys) - min(ys) + 160,
        ]
    result = {
        "id": map_id,
        "name": name,
        "variant": variant,
        "difficulty": public.get("difficulty", "Easy"),
        "task_count": task_count,
        "node_count": len(locations),
        "edge_count": len(edges),
        "current": map_id == CURRENT_MAP,
        "terrain": terrain,
        "station_game": bool(filename),
        "play_url": "/play?map=" + map_id,
        "version": public.get("version", ""),
        "materials": list(public.get("kinds", {}).values()),
        "map": {
            "locations": locations,
            "edges": edges,
            "view_box": bounds,
            "ferry_edges": public.get("ferry_edges", []),
            "processing_regions": public.get("processing_regions", {}),
        },
        "trigger_nodes": sorted(set(triggers)),
    }
    if geographic:
        result["map"].update(geographic)
        result["terrain_asset"] = geographic["terrain_asset"]
    return result


def map_detail(map_id):
    return deepcopy(_detail(map_id))


def map_listing():
    result = []
    for map_id in MAPS:
        try:
            result.append(
                {
                    key: value
                    for key, value in _detail(map_id).items()
                    if key not in ("map", "trigger_nodes")
                }
            )
        except ValueError:
            continue
    return result


@lru_cache(maxsize=1)
def _human_names():
    names = {}
    for label, _, filename in MAPS.values():
        path = DATA / filename
        if path.is_file():
            public = json.loads(path.read_text(encoding="utf-8"))["public"]
            names[public["name"]] = label
    return names


def human_map_name(public):
    """Website projection only; never mutate a frozen observation or design."""
    return _human_names().get(public["name"], public["name"])
