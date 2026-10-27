"""Check whether a self-authored skill body arrived before station selection."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


def strings(value, depth=0):
    """Tool output can itself be JSON encoded inside a Responses input string."""
    if depth > 5:
        return
    if isinstance(value, str):
        yield value
        try:
            embedded = json.loads(value)
        except (ValueError, TypeError, RecursionError):
            return
        yield from strings(embedded, depth+1)
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child, depth+1)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child, depth+1)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skill-file", default="skills/games/cartography-game/SKILL.md")
    args = parser.parse_args()
    relative = Path(args.skill_file)
    if relative.is_absolute() or ".." in relative.parts:
        parser.error("skill-file must stay within the native memory directory")
    root = args.run.resolve()
    pilot = read(root / "pilot.json")
    assert pilot["status"] == "completed"
    assert not (root / "baseline" / relative).exists(), "Skill must be newly authored in this run"
    decisions = {row["name"]: row for row in read(args.decisions)["rows"]}
    previous = root / "baseline"
    cases = []
    for session in pilot["sessions"]:
        if session["condition"] == "clear":
            continue
        skill = previous / relative
        row = {"task": session["task_id"], "input_skill_exists": skill.exists(),
               "verified_before_first_postcollection_station": False}
        window = decisions[session["name"]]["native_tool_windows"]["before_first_postcollection_station"]
        requests = window["native_skill_view_requests"] if window else []
        requested = any(view.get("name", "").endswith(relative.parent.name) for view in requests)
        row["predecision_skill_view_requested"] = requested
        if skill.exists() and requested:
            text = skill.read_text(encoding="utf-8")
            body = text.split("---", 2)[-1].strip() if text.startswith("---") else text.strip()
            row.update(skill_file=relative.as_posix(), skill_sha256=sha256(skill.read_bytes()).hexdigest())
            if body:
                for index in range(1, window["model_request_count"]+1):
                    request = root / "sessions" / session["name"] / "model" / f"{index:03d}-request.json"
                    if any(body in value for value in strings(read(request))):
                        row.update(verified_before_first_postcollection_station=True, request_number=index,
                                   request_sha256=sha256(request.read_bytes()).hexdigest())
                        break
        cases.append(row)
        previous = root / "sessions" / session["name"] / "memory-after"
    artifact = {"kind": "self_authored_skill_body_delivery_not_internal_causal_use", "agent": pilot.get("agent", "ga"),
                "matching": "Complete Markdown body after YAML frontmatter; only outer whitespace stripped. Nested JSON tool strings decoded.",
                "coverage": "All main tasks, including absent skills and unverified reads", "cases": cases,
                "source_pilot_sha256": sha256((root / "pilot.json").read_bytes()).hexdigest(),
                "source_decisions_sha256": sha256(args.decisions.read_bytes()).hexdigest(),
                "analysis_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(artifact, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"main_tasks": len(cases), "verified_skill_body_deliveries": sum(r["verified_before_first_postcollection_station"] for r in cases)}))


if __name__ == "__main__":
    main()
