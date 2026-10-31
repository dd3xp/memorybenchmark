"""Public station types with hidden type-to-capability mappings and ordinary tasks.

This creates a new design. The v3 map and its published agent runs stay intact.
Dependencies are evaluator metadata, never part of a task or public observation.
"""
import json
from pathlib import Path

from scripts.build_easy20_linked_map import build as linked_map


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "memorybenchmark/data/station_easy20_reuse.json"

# Each kind and collection point occurs five times. The last eight commissions
# move each kind to the opposite region; sites of the same type remain equivalent.
ITINERARIES = [
    (("P", "profile"), ("R", "bearing")),
    (("U", "vegetation"), ("X", "drainage")),
    (("Q", "profile"), ("V", "vegetation")),
    (("S", "bearing"), ("Y", "drainage")),
    (("P", "shore"), ("R", "elevation")),
    (("U", "lithology"), ("X", "contour")),
    (("Q", "shore"), ("V", "lithology")),
    (("S", "elevation"), ("Y", "contour")),
    (("Q", "profile"), ("V", "vegetation")),
    (("S", "bearing"), ("Y", "drainage")),
    (("Q", "shore"), ("V", "lithology")),
    (("S", "elevation"), ("Y", "contour")),
    (("U", "profile"), ("R", "drainage")),
    (("X", "bearing"), ("P", "vegetation")),
    (("V", "shore"), ("S", "contour")),
    (("Y", "elevation"), ("Q", "lithology")),
    (("U", "profile"), ("R", "contour")),
    (("X", "bearing"), ("P", "lithology")),
    (("U", "shore"), ("R", "drainage")),
    (("X", "elevation"), ("P", "vegetation")),
]


def build():
    design = linked_map()
    public = design["public"]
    public.update(version="lanting-easy20-fixed-types-v5", name="岚汀丘地 · 同型联程")
    rename = {"A": "A1", "B": "B1", "N1": "C1", "N2": "D1",
              "F": "A2", "G": "B2", "S1": "C2", "S2": "D2",
              "D": "E1", "E": "F1", "E1": "G1", "E2": "H1",
              "H": "E2", "K": "F2", "W1": "G2", "W2": "H2"}
    for old, new in list(rename.items()):
        for index in (1, 2):
            rename[f"{old.lower()}p{index}"] = f"{new.lower()}p{index}"
    public["locations"] = {rename.get(id_, id_): data for id_, data in public["locations"].items()}
    for id_, data in public["locations"].items():
        if data["kind"] == "station":
            data.update(name=f"{id_[0]} 型站 · {id_}", station_type=id_[0])
        elif data.get("transit"):
            data["name"] = f"{id_.split('p')[0].upper()} 支路第 {id_[-1]} 段"
    public["edges"] = [[rename.get(a, a), rename.get(b, b), w] for a, b, w in public["edges"]]
    public["station_types"] = {t: {"name": f"{t} 型", "stations": [f"{t}1", f"{t}2"]} for t in "ABCDEFGH"}
    public["capability_groups"] = {
        "NS": {"name": "南北同型站网", "stations": [f"{t}{i}" for t in "ABCD" for i in (1, 2)],
               "station_types": list("ABCD"), "kinds": ["profile", "shore", "vegetation", "lithology"],
               "counts": {k: 2 for k in ("profile", "shore", "vegetation", "lithology")}},
        "EW": {"name": "东西同型站网", "stations": [f"{t}{i}" for t in "EFGH" for i in (1, 2)],
               "station_types": list("EFGH"), "kinds": ["bearing", "elevation", "drainage", "contour"],
               "counts": {k: 2 for k in ("bearing", "elevation", "drainage", "contour")}},
    }
    public["rules"] = [
        "每封委托有两段公开行程，按顺序各到目标自动采集、在匹配站处理；两段完成后回 C 提交。第一段处理成功即进入第二段，不用中途回营。",
        "目标是在操作预算内完成委托，并尽量减少道路总距离；距离相同时减少操作。允许自由探索、查询和改道。",
        "地图公开 A 至 H 八种站型及每型两座站的位置。同型站功能完全一致；类型字母没有语义，站型与处理能力的对应关系是本地图的固定属性，跨委托、跨 session 以及重复实验均不改变。",
        "A/B/C/D 型在南北各有一站，分别支持剖面、岸线、植被、岩性中的一种；E/F/G/H 型在东西各有一站，分别支持方位、高程、水系、等高线中的一种。每个站网内四种能力与四种站型一一对应，具体配对不公开。",
        "只有现场 inspect 或 process 交付当前站的实际能力和公开站型。此反馈可以适用于远处同型站，但不会自动写入你的持久记忆。地图、站名和新委托不提供隐藏配对或历史反馈。",
        "各站在独立支路末端；所有中间地点都要实际移动，不能跳过。不匹配的 process 保留当前段原始资料，也公开该站型能力。",
        "两段资料分别采集、处理；提前走过下一段目标不算采集下一段资料。每项最多八十八次操作，read 免费。",
        "每项开始新的 session，只有 Agent 自主维护的原生记忆跨 session；历史对话和环境反馈不会随地图传递。失败时已交付的经验仍然有效。",
    ]
    tasks = {}
    for index, itinerary in enumerate(ITINERARIES, 1):
        stages = [{"target": target, "required_kind": kind} for target, kind in itinerary]
        tasks[f"T{index}"] = {"name": f"联程巡测 {index:02d}", "start": "C", "submit_at": "C",
                              **stages[0], "stages": stages, "max_steps": 88}
    design.update(design_id=design["public"]["version"], tasks=tasks,
                  world_generator="station_type_permutations",
                  fixed_world="omega_15_05",
                  status="fixed_map_pending_native_agent_calibration")
    design["evaluation"] = {
        "experience_protocol": "station-experience-opportunity-1",
        "opportunity_basis": "Actual delivered feedback before this session; inferred facts are reported separately from direct observations.",
        "success_guarantee": "Successful processing reveals a matching type. All physical instances of that public type are equivalent, including unvisited ones. It does not guarantee saving, retrieval, reuse, or benefit.",
        "failure_policy": "Use only feedback actually delivered, including failed processing. No answer injection or compulsory catch-up.",
        "stream_policy": "Fixed twenty-task stream independent of agent choices. Every commission is ordinary play; no separate investigation or training phase.",
        "diagnostic_scope": "Descriptive acquisition/reuse and paired costs. This design does not establish controlled retention or interference scores.",
    }
    design["presentation"]["subtitle"] = "八种站型 · 同型异站与跨委托复用"
    return design


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
