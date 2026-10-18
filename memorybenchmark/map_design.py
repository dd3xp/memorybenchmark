"""Human-only, read-only map inspection. Never imported by the agent bridge."""
from copy import deepcopy
from functools import lru_cache

from .validation import reference_route
from .worlds import load_scenario, submission_camps, task_goals


MAP_NAMES = {"lake-easy": "雾汀湖", "valley": "谷地校准原型", "river": "渡口校准原型"}


@lru_cache(maxsize=8)
def _design(scenario):
    world, tasks = load_scenario(scenario)
    public_id = world.get("public_id", scenario)
    rows = []
    static = not world.get("passages") and not any(h.get("conditions") for h in world.get("hazards", {}).values())
    for task_id, task in tasks.items():
        reference = None
        if static:
            plan = reference_route(world, task)
            position, path, distance, encounters = task["start"], [task["start"]], 0, {}
            distances = {frozenset((a, b)): d for a, b, d in world["edges"]}
            for action in plan["actions"]:
                if action["type"] != "move":
                    continue
                target = action["target"]
                distance += distances[frozenset((position, target))]
                position = target
                path.append(target)
                if target in world.get("hazards", {}):
                    encounters[target] = encounters.get(target, 0) + 1
            reference = {"path": path, "effort": plan["effort"], "distance": distance,
                         "steps": len(plan["actions"]), "encounters": encounters,
                         "tools": [a["target"] for a in plan["actions"] if a["type"] == "take"]}
        rows.append({"id": task_id, "name": task["name"], "instruction": task["instruction"],
                     "start": task["start"], "goals": list(task_goals(task)),
                     "submit_at": list(submission_camps(world, task)),
                     "stamina": task.get("stamina", 100), "reference": reference})

    triggers = []
    for location, hazard in world.get("hazards", {}).items():
        tools = []
        for tool_id, tool in world.get("tools", {}).items():
            effort = tool["mitigates"].get(hazard["kind"], hazard["extra_effort"])
            if effort < hazard["extra_effort"]:
                tools.append({"id": tool_id, "name": tool["name"], "effort": effort,
                              "depots": [n for n, stock in world.get("depots", {}).items() if tool_id in stock]})
        opportunities = []
        for row in rows:
            count = (row["reference"] or {}).get("encounters", {}).get(location, 0)
            if count:
                opportunities.append({"task_id": row["id"], "encounters": count,
                                      "preparation_at": row["start"],
                                      "role": "first_contact" if not opportunities else "reuse_opportunity"})
        triggers.append({"id": "hazard:" + location, "kind": "hazard", "location": location,
                         "name": hazard["name"], "extra_effort": hazard["extra_effort"],
                         "conditions": hazard.get("conditions", {}), "tools": tools,
                         "opportunities": opportunities})
    for index, passage in enumerate(world.get("passages", [])):
        triggers.append({"id": f"passage:{index}", "kind": "passage", "edge": passage["edge"],
                         "name": "条件通行", "conditions": passage["conditions"],
                         "feedback": passage["feedback"], "tools": [], "opportunities": []})
    return {"audience": "human_design_review", "scenario": public_id,
            "name": world.get("name", MAP_NAMES[public_id]), "version": world["version"],
            "difficulty": world.get("difficulty"), "view_box": world.get("view_box", [0, 0, 830, 510]),
            "maps": [{"id": key, "name": name} for key, name in MAP_NAMES.items()],
            "map": {"nodes": [{"id": key, **{k: v for k, v in value.items() if k in ("name", "x", "y", "kind")}}
                              for key, value in world["locations"].items()],
                    "edges": [[a, b] for a, b, _ in world["edges"]],
                    "distances": [{"source": a, "target": b, "distance": d} for a, b, d in world["edges"]]},
            "tasks": rows, "triggers": triggers,
            "reference_scope": "full_information_static_feasibility" if static else "unavailable_dynamic_conditions"}


def map_design(scenario="lake-easy"):
    # Return a copy so an HTTP consumer cannot mutate a cached design or game.
    return deepcopy(_design(scenario))
