"""Evaluator-side scenario loading; full configurations never go to clients."""
from copy import deepcopy
import json
from pathlib import Path

RIVER_WORLD = {
    "version": "river-calibration-1",
    "locations": {
        "S": {"name":"起点","x":80,"y":250}, "J": {"name":"岔路口","x":240,"y":250},
        "F": {"name":"渡口","x":410,"y":250}, "R": {"name":"对岸","x":560,"y":250},
        "K": {"name":"测绘点","x":730,"y":250}, "H": {"name":"山路","x":480,"y":410},
        "U": {"name":"支谷","x":240,"y":100}, "V": {"name":"谷地深处","x":450,"y":100}
    },
    "edges": [["S","J",2],["J","F",1],["F","R",1],["R","K",1],["J","H",2],["H","K",2],["J","U",1],["U","V",1]],
    "weather": [[0,"rain","night"],[120,"clear","day"],[205,"snow","day"],[337,"rain","night"]],
    "passages": [{"edge":["F","R"],"conditions":{"weather":"rain","period":"night"},"feedback":"渡河受阻：本渡口在雨夜无法通行。你仍在原地。"}],
    "hazards": {}, "tools": {}, "depots": {}
}
RIVER_TASKS = {
    "T1": {"name":"渡口勘测","goal":"F","start":"S","instruction":"前往渡口 F 完成地理记录，然后提交。到达即自动测绘。"},
    "T2": {"name":"对岸测绘","goal":"K","start":"S","instruction":"前往测绘点 K 完成地理记录，然后提交。自行选择路线。"}
}

def load_scenario(name="valley"):
    if name == "river":
        return deepcopy(RIVER_WORLD), deepcopy(RIVER_TASKS)
    if name != "valley":
        raise ValueError("未知场景。")
    data = json.loads((Path(__file__).parent / "data" / "valley.json").read_text(encoding="utf-8"))
    return data["world"], data["tasks"]
