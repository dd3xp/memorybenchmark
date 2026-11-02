"""Build the first themed Easy map without modifying any frozen prototype.

The public layer contains only fictional geography, evidence names and station
types. Candidate worlds, the fixed fixture and dependencies stay evaluator-side.
"""
from itertools import permutations
import json
from pathlib import Path

from scripts.build_easy20_reuse_map import ITINERARIES


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "memorybenchmark/data/nessie_easy20.json"
VERSION = "nessie-easy-1.0"
KIND_IDS = {
    "profile": "wake", "shore": "shoreprint", "vegetation": "reeds", "lithology": "residue",
    "bearing": "echo", "elevation": "image", "drainage": "thermal", "contour": "vibration",
}
KINDS = {
    "wake": "异常尾流", "shoreprint": "岸边压痕", "reeds": "折苇痕迹", "residue": "附着物样本",
    "echo": "水下回声", "image": "远距影像", "thermal": "热源记录", "vibration": "岸侧振动",
}
TASK_NAMES = [
    "北湾异常", "南汀折苇", "双岸尾流", "两岸回声", "浅滩压痕",
    "浮屑复核", "岸边印记", "夜影核查", "尾流再访", "回声复测",
    "压痕复查", "夜影再访", "南湾追踪", "东岸芦影", "跨岸对照",
    "北湾残留", "南汀异响", "东岸浮屑", "压痕与热迹", "影像与折苇",
]

# A schematic SW--NE glacial lake. These are invented, public game locations,
# not the coordinates or real names of infrastructure around Loch Ness.
CORE = {
    "C": ("水怪调查营地", "camp", 1830, 110),
    "NC": ("北口堤道", "junction", 1700, 180),
    "NW": ("北湾西岔", "junction", 1390, 180),
    "WN": ("西岬路口", "junction", 1220, 360),
    "WM": ("西岸岭道", "junction", 950, 580),
    "WS": ("苔溪坡口", "junction", 650, 850),
    "SW": ("南汀西岔", "junction", 450, 1110),
    "SC": ("南口石桥", "junction", 570, 1390),
    "SE": ("南汀东岔", "junction", 820, 1310),
    "ES": ("杉湾路口", "junction", 1100, 1090),
    "EM": ("东崖林道", "junction", 1360, 850),
    "EN": ("回声岬口", "junction", 1640, 620),
    "NE": ("北湾东岔", "junction", 1810, 390),
}
CORE_EDGES = [
    ("C", "NC", 1), ("NC", "NW", 2), ("NW", "WN", 2), ("WN", "WM", 3),
    ("WM", "WS", 3), ("WS", "SW", 2), ("SW", "SC", 2), ("SC", "SE", 2),
    ("SE", "ES", 2), ("ES", "EM", 3), ("EM", "EN", 3), ("EN", "NE", 2),
    ("NE", "NC", 2),
]
SURVEYS = {
    "P": ("北湾苇滩", "NW", 1480, 270, 1),
    "Q": ("北岬旧码头", "NE", 1710, 430, 1),
    "R": ("西岬观测台", "WN", 1120, 490, 1),
    "S": ("苔溪滩头", "WS", 760, 850, 1),
    "U": ("南汀泥湾", "SW", 470, 1230, 1),
    "V": ("南口碎石滩", "SE", 850, 1170, 1),
    "X": ("东崖水线", "EM", 1270, 960, 1),
    "Y": ("林湾静水点", "EN", 1550, 750, 1),
}
STATIONS = {
    "A1": ("NW", 1190, 80, 3), "B1": ("NW", 1350, 50, 4),
    "C1": ("NE", 1990, 290, 3), "D1": ("NE", 2010, 450, 4),
    "A2": ("SW", 240, 1060, 3), "B2": ("SW", 300, 1270, 4),
    "C2": ("SE", 740, 1510, 3), "D2": ("SE", 940, 1480, 4),
    "E1": ("WN", 1020, 230, 3), "F1": ("WN", 960, 380, 4),
    "G1": ("WS", 420, 820, 3), "H1": ("WS", 480, 1000, 4),
    "E2": ("EN", 1800, 540, 3), "F2": ("EN", 1940, 640, 4),
    "G2": ("ES", 1300, 1170, 3), "H2": ("ES", 1280, 1330, 4),
}


def build():
    locations = {id_: {"name": name, "kind": kind, "x": x, "y": y}
                 for id_, (name, kind, x, y) in CORE.items()}
    edges = [list(edge) for edge in CORE_EDGES]
    for id_, (name, fork, x, y, weight) in SURVEYS.items():
        locations[id_] = {"name": name, "kind": "survey", "x": x, "y": y}
        edges.append([fork, id_, weight])
    for id_, (fork, x, y, distance) in STATIONS.items():
        label = "水怪勘测站" if id_[0] in "ABCD" else "水怪研判站"
        locations[id_] = {"name": f"{id_[0]} 型{label} · {id_}", "kind": "station",
                          "station_type": id_[0], "x": x, "y": y}
        origin = locations[fork]
        last = fork
        transit_count = 1 if distance == 3 else 2
        for index in range(1, transit_count+1):
            transit = f"{id_.lower()}p{index}"
            locations[transit] = {"name": f"{id_} 支路第 {index} 段", "kind": "junction", "transit": True,
                                  "x": round(origin["x"] + (x-origin["x"])*index/(transit_count+1)),
                                  "y": round(origin["y"] + (y-origin["y"])*index/(transit_count+1))}
            edges.append([last, transit, 1])
            last = transit
        edges.append([last, id_, distance-transit_count])
    group_specs = [("shore", "踪迹勘测站网", "ABCD", ["wake", "shoreprint", "reeds", "residue"]),
                   ("signal", "信号研判站网", "EFGH", ["echo", "image", "thermal", "vibration"])]
    groups = {key: {"name": name, "station_types": list(types),
                    "stations": [f"{t}{i}" for t in types for i in (1, 2)],
                    "kinds": kinds, "counts": {kind: 2 for kind in kinds}}
              for key, name, types, kinds in group_specs}
    # This fixture is authored once and shared by every run. The other 575
    # assignments are evaluator hypotheses, not per-run randomization.
    fixture = {"A": "reeds", "B": "residue", "C": "wake", "D": "shoreprint",
               "E": "image", "F": "echo", "G": "vibration", "H": "thermal"}
    indices = [list(permutations(kinds)).index(tuple(fixture[t] for t in types))
               for _, _, types, kinds in group_specs]
    fixed_world = "omega_" + "_".join(f"{i:02d}" for i in indices)
    tasks = {}
    for index, itinerary in enumerate(ITINERARIES, 1):
        stages = [{"target": target, "required_kind": KIND_IDS[kind]} for target, kind in itinerary]
        tasks[f"T{index}"] = {"name": TASK_NAMES[index-1], "start": "C", "submit_at": "C",
                              **stages[0], "stages": stages, "max_steps": 88}
    public = {
        "version": VERSION, "name": "尼斯湖水怪", "difficulty": "Easy", "terrain": "nessie",
        "view_box": [0, 0, 2200, 1600],
        "vocabulary": {"survey": "踪迹调查点", "station": "勘测基站", "collect": "调查", "process": "研判", "item": "踪迹", "submit": "交付"},
        "rules": [
            "每项水怪调查委托有两段行程。依次到目标点自动记录本段指定踪迹，在支持该类踪迹的基站研判；两段完成后回 C 营地交付一次。",
            "目标是在操作预算内完成委托，优先减少道路总距离，距离相同时减少操作。全图从第一项起可自由探索，不设教学或解锁阶段。",
            "A 至 H 是八种公开站型，每型两座站。同型站支持相同踪迹；字母和站名不暗示具体能力。同一地图的能力配对跨委托、跨 session、跨 Agent 和重复实验保持固定。",
            "A/B/C/D 型分别支持异常尾流、岸边压痕、折苇痕迹、附着物样本中的一种；E/F/G/H 型分别支持水下回声、远距影像、热源记录、岸侧振动中的一种。每个站网内四种站型与四种能力一一对应，具体配对需交互获知。",
            "只有抵达基站后 inspect 或 process 才反馈该站型的实际能力。inspect 查询消耗一次操作；process 研判不匹配也消耗一次操作，原始踪迹仍保留。",
            "在任一同型站获得的能力经验可以用于另一座同型站。地理图始终可见，但不记录历史能力、研判反馈或替你保存经验。",
            "每段到目标自动采集，研判成功后才进入下一段；提前经过后续目标不算完成后续调查。中间支路节点必须逐点移动，湖面没有横穿捷径。",
            "每项从 C 开始，位置、资料、对话和工作记忆重置；只有 Agent 自主保存的持久记忆跨 session。失败后继续固定任务流，只能保留实际经历过的经验，不补发答案。",
            "一项最多八十八次操作，read 免费。报告可疑踪迹不等于证实水怪存在；游戏只验证调查流程和经验复用。",
        ],
        "kinds": KINDS, "capability_groups": groups,
        "station_types": {t: {"name": f"{t} 型", "stations": [f"{t}1", f"{t}2"]} for t in "ABCDEFGH"},
        "locations": locations, "edges": edges,
    }
    return {
        "design_id": VERSION, "status": "formal_easy_candidate_pending_native_agent_calibration",
        "world_generator": "station_type_permutations", "fixed_world": fixed_world,
        "public": public, "tasks": tasks,
        "presentation": {"terrain": "nessie", "regions": [
            {"name": "北湾", "x": 1570, "y": 90}, {"name": "西岬", "x": 830, "y": 450},
            {"name": "南汀", "x": 430, "y": 1450}, {"name": "东崖", "x": 1650, "y": 990},
        ]},
        "evaluation": {
            "experience_protocol": "station-experience-opportunity-1",
            "opportunity_basis": "Actual delivered feedback before this session. Direct observation and logical inference are reported separately.",
            "failure_policy": "Continue the fixed stream using only actual delivered feedback; no compulsory catch-up or answer injection.",
            "stream_policy": "Twenty ordinary commissions, forty stages. Geographic access is open from T1. Every condition starts from its own fresh original agent memory.",
            "diagnostic_scope": "Acquisition, retrieval delivery, station commitments and route costs; not a large-memory or controlled interference condition.",
        },
        "provenance": {
            "geography": "Loch Ness-inspired SW--NE lake, separate shore corridors and forest/gorge spurs; schematic, fictional nodes and roads, no real navigation claims.",
            "sources": [
                {"title": "Forestry and Land Scotland: Great Glen forests", "url": "https://forestryandland.gov.scot/visit/forests-by-region/forests-in-the-great-glen"},
                {"title": "Forestry and Land Scotland: Farigaig", "url": "https://forestryandland.gov.scot/visit/destinations/farigaig"},
                {"title": "Highland Council: Paths around Foyers", "url": "https://www.highland.gov.uk/download/downloads/id/1088/paths_around_foyers.pdf"},
            ],
            "private_boundary": "Source names, coordinates, hidden assignment IDs and evaluator dependencies are not injected by the game adapter.",
        },
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
