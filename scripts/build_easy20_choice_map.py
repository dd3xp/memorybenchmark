"""Build the deterministic public route-choice map; hidden allocations stay random."""
from copy import deepcopy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "memorybenchmark/data/station_easy20_choice.json"


def build():
    old = json.loads((ROOT / "memorybenchmark/data/station_easy20.json").read_text(encoding="utf-8"))
    public = deepcopy(old["public"])
    public.update(version="lanting-easy20-choice-v2", name="岚汀丘地 · 四站巡测", view_box=[0, 0, 2000, 1700])
    public["rules"] = [
        "每项从 C 出发，到目标自动采集，在支持该资料的站处理，再回 C 提交；旧资料不能代替本次采集。",
        "每组有四个处理站，两种公开资料各有两个匹配站。四组独立分配，一轮二十项中保持不变。知道一站不能确定其余三站。",
        "地图、道路距离和各组候选站均公开；只有 inspect 或实际 process 交付站点能力。地名、字母和远近不能确定能力。",
        "道路按标示距离通行，画面上的直线长度不代表距离。可以沿环路自由探索、换站或返回。",
        "inspect 与 process 各占一次操作；不支持的处理保留资料。每项最多二十四次操作，read 免费。",
        "每项清空位置、资料、处理状态和临时上下文。只有 Agent 自主保存的记忆跨 session 传递；失败后已收到的反馈仍算实际经历。",
    ]
    locations = {"C": {"name": "手记营地", "kind": "camp", "x": 1120, "y": 970},
                 "J": {"name": "风标岔口", "kind": "junction", "x": 1000, "y": 850}}
    edges = [["C", "J", 1]]
    regions = []
    definitions = [
        ("AB", "N", ["A", "B", "N1", "N2"], ["P", "Q"], 0),
        ("DE", "E", ["D", "E", "E1", "E2"], ["R", "S"], 1),
        ("FG", "S", ["F", "G", "S1", "S2"], ["U", "V"], 2),
        ("HK", "W", ["H", "K", "W1", "W2"], ["X", "Y"], 3),
    ]
    for key, prefix, stations, targets, rotation in definitions:
        group = public["capability_groups"][key]
        group.update(stations=stations, counts={kind: 2 for kind in group["kinds"]})
        gate, left, right = "J" + prefix, prefix + "L", prefix + "R"
        template = [(gate, 0, -220, "junction"), (left, -180, -400, "junction"),
                    (right, 180, -400, "junction"), (stations[0], -300, -480, "station"),
                    (stations[1], -200, -650, "station"), (stations[2], 300, -480, "station"),
                    (stations[3], 200, -650, "station"), (targets[0], -80, -330, "survey"),
                    (targets[1], 80, -330, "survey")]
        for node, x, y, kind in template:
            for _ in range(rotation):
                x, y = -y, x
            name = old["public"]["locations"].get(node, {}).get("name")
            if not name:
                name = f"{node} 处理站" if kind == "station" else f"{group['name']}侧岔{1 if node == left else 2}"
            locations[node] = {"name": name, "kind": kind, "x": 1000 + x, "y": 850 + y}
        edges.extend([["J", gate, 1], [gate, left, 2], [gate, right, 2], [left, right, 3],
                      [left, stations[0], 1], [left, stations[1], 2],
                      [right, stations[2], 1], [right, stations[3], 2],
                      [left, targets[0], 1], [right, targets[1], 1], [targets[0], targets[1], 3]])
        x, y = 0, -740
        for _ in range(rotation):
            x, y = -y, x
        regions.append({"name": group["name"], "x": 1000 + x, "y": 850 + y})
    public.update(locations=locations, edges=edges)
    tasks = deepcopy(old["tasks"])
    for task in tasks.values():
        task["max_steps"] = 24
    return {"design_id": public["version"], "status": "route_choice_design_pending_native_agent_calibration",
            "world_generator": "independent_balanced_allocations", "public": public,
            "presentation": {"subtitle": "四站巡测 · 带权环路与匹配选择", "regions": regions}, "tasks": tasks}


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
