"""Human map browser: allowlisted geography, never agent task configuration."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from .worlds import load_scenario

DATA = Path(__file__).parent / "data"
MAPS = {
    "easy20": ("岚汀丘地", "同型站", "station_easy20_reuse.json"),
    "linked20": ("岚汀丘地", "联程", "station_easy20_linked.json"),
    "choice20": ("岚汀丘地", "多站点", "station_easy20_choice.json"),
    "station20": ("岚汀丘地", "初版", "station_easy20.json"),
    "lake-easy": ("雾汀湖", "工具经验", None),
    "valley": ("谷地", "校准", None),
    "river": ("渡口", "校准", None),
    "capability-v2": ("站点原型", "第二版", DATA.parents[1] / "design/station_capability_v2.json"),
    "capability-v1": ("站点原型", "第一版", DATA.parents[1] / "design/station_capability_v1.json"),
}


def station_design(map_id):
    if map_id not in MAPS or MAPS[map_id][2] is None:
        raise ValueError("地图不存在。")
    source = MAPS[map_id][2]
    path = source if isinstance(source, Path) else DATA / source
    if not path.is_file():
        raise ValueError("地图资源未安装。")
    return path


@lru_cache(maxsize=16)
def _detail(map_id):
    if map_id not in MAPS:
        raise ValueError("地图不存在。")
    name, variant, filename = MAPS[map_id]
    if filename:
        design = json.loads(station_design(map_id).read_text(encoding="utf-8"))
        public = design["public"]
        locations, edges = public["locations"], public["edges"]
        terrain = "field"
        triggers = [key for key, node in locations.items() if node.get("kind") == "station"]
        bounds = public.get("view_box")
        task_count = len(design["tasks"])
    else:
        world, tasks = load_scenario(map_id)
        # Do not send rules, schedules, tools or hazard answers with geography.
        locations = {key: {field: value for field, value in node.items()
                         if field in ("name", "x", "y", "kind", "terrain")}
                     for key, node in world["locations"].items()}
        for key in world.get("camps", []):
            locations[key]["kind"] = "camp"
        edges, terrain, bounds = world["edges"], "lake" if map_id == "lake-easy" else "plain", None
        triggers = list(world.get("hazards", {}))
        triggers += [point for passage in world.get("passages", []) for point in passage["edge"]]
        task_count = len(tasks)
    if bounds is None:
        xs = [node["x"] for node in locations.values()]
        ys = [node["y"] for node in locations.values()]
        bounds = [min(xs) - 80, min(ys) - 80, max(xs) - min(xs) + 160, max(ys) - min(ys) + 160]
    return {"id": map_id, "name": name, "variant": variant, "difficulty": "Easy",
            "task_count": task_count, "node_count": len(locations), "edge_count": len(edges),
            "current": map_id == "easy20", "terrain": terrain,
            "play_url": "/play?map=" + map_id,
            "map": {"locations": locations, "edges": edges, "view_box": bounds},
            "trigger_nodes": sorted(set(triggers))}


def map_detail(map_id):
    return deepcopy(_detail(map_id))


def map_listing():
    result = []
    for map_id in MAPS:
        try:
            result.append({key: value for key, value in _detail(map_id).items() if key not in ("map", "trigger_nodes")})
        except ValueError:
            continue
    return result
