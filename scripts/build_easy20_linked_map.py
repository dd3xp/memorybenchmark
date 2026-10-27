"""Build a public two-stage itinerary with persistent, privately assigned capabilities."""
from copy import deepcopy
import json
from pathlib import Path

from scripts.build_easy20_choice_map import build as choice_map

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "memorybenchmark/data/station_easy20_linked.json"


def build():
    design = deepcopy(choice_map())
    public = design["public"]
    public.update(version="lanting-easy20-linked-v3", name="岚汀丘地 · 联程巡测")
    edges = []
    for a, b, weight in public["edges"]:
        if public["locations"][b]["kind"] != "station":
            edges.append([a, b, weight])
            continue
        start, end = public["locations"][a], public["locations"][b]
        previous = a
        for index in (1, 2):
            node = f"{b.lower()}p{index}"
            public["locations"][node] = {
                "name": f"{b} 支路第 {index} 段", "kind": "junction", "transit": True,
                "x": round(start["x"] + (end["x"] - start["x"]) * index / 3),
                "y": round(start["y"] + (end["y"] - start["y"]) * index / 3),
            }
            edges.append([previous, node, 1]); previous = node
        edges.append([previous, b, weight])
    public["edges"] = edges
    public["rules"] = [
        "每封委托有两段公开行程，按顺序各到目标自动采集、在匹配站处理；两段完成后回 C 提交。第一段处理成功即进入第二段，不用中途回营。",
        "目标是在操作预算内完成委托，并尽量减少道路总距离；距离相同时减少操作。允许自由探索、查询和改道。",
        "四组各有四座站，两种资料各有两座匹配站；能力均衡独立分配，一轮中稳定。地点、字母、道路长短不能确定能力。",
        "地图和两段任务要求全部公开；站点能力只在现场 inspect 或 process 后交付。没有全图经验广播，没有必做查询。",
        "各站在独立支路末端；所有中间地点都要实际移动，不能跳过。不匹配的 process 保留当前段原始资料，也公开该站能力。",
        "两段资料分别采集、处理；提前走过下一段目标不算采集下一段资料。每项最多七十二次操作，read 免费。",
        "每项开始新的 session，只有 Agent 自主维护的原生记忆跨 session；历史对话和环境反馈不会随地图传递。失败时已交付的经验仍然有效。",
    ]
    definitions = {
        "AB": ("P", "Q"), "DE": ("R", "S"), "FG": ("U", "V"), "HK": ("X", "Y"),
    }
    pairs = [("AB", "DE"), ("FG", "HK"), ("AB", "FG"), ("DE", "HK"), ("AB", "HK"), ("DE", "FG")]
    kind_order = [0, 1, 0, 1, 1, 0, 0, 1, 0, 1]
    target_order = [0, 1, 0, 1, 1, 0, 1, 0, 1, 0]
    occurrences = dict.fromkeys(definitions, 0)
    tasks = {}
    for index in range(20):
        stages = []
        for group in pairs[index % len(pairs)]:
            occurrence = occurrences[group]; occurrences[group] += 1
            stages.append({"target": definitions[group][target_order[occurrence]],
                           "required_kind": public["capability_groups"][group]["kinds"][kind_order[occurrence]]})
        tasks[f"T{index+1}"] = {"name": f"联程巡测 {index+1:02d}", "start": "C", "submit_at": "C",
                               **stages[0], "stages": stages, "max_steps": 72}
    design.update(design_id=public["version"], status="linked_itinerary_pending_native_agent_calibration", tasks=tasks)
    design["native_session_budget"] = {"main_model_calls": 100}
    design["presentation"]["subtitle"] = "联程巡测 · 两段委托与支路选择"
    return design


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
