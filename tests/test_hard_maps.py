"""Condition-scoped feedback, evidence, scoring, native budgets and web play."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen

from memorybenchmark.map_catalog import station_design, map_detail
from memorybenchmark.prototypes.station_capability import (
    StationGame,
    load_design,
    map_world,
)
from memorybenchmark.prototypes.station_session import StationSession
from memorybenchmark.prototypes.station_knowledge import (
    evidence_support,
    historical_status,
    supports,
)
from memorybenchmark.prototypes.station_routes import walk, shortest_route
from memorybenchmark.prototypes.station_metrics import score_stream
from memorybenchmark.prototypes.station_experience import experience_opportunities
from memorybenchmark.prototypes.station_choice import station_decisions
from memorybenchmark.server import make_server


class HardMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.designs = {
            key: load_design(station_design(key + "-hard"))
            for key in ("orcia", "hampi", "angkor")
        }

    def pair(self):
        design = load_design(
            Path(__file__).resolve().parents[1]
            / "memorybenchmark/data/hampi_hard48.json"
        )
        assignment = design["private_worlds"][map_world(design)]
        station, kind = next(
            (s, k)
            for s, table in assignment.items()
            for k in table["catalogue"]
            if k not in table["verify"]
        )
        targets = [
            s for s, p in design["public"]["locations"].items() if p["kind"] == "survey"
        ]
        design["tasks"] = {}
        for i, r in enumerate(("catalogue", "verify")):
            stage = {"target": targets[i], "required_kind": kind, "requirement": r}
            design["tasks"][f"T{i+1}"] = {
                "name": "条件隔离验收",
                "start": "C",
                "submit_at": "C",
                **stage,
                "stages": [stage],
                "max_steps": 288,
            }
        return design, station, kind

    def collect(self, game):
        walk(game, game.task["target"])
        game.step({"type": "survey"})

    def test_authoring_counts_balanced_contexts_and_useful_replicas(self):
        for design in self.designs.values():
            p = design["public"]
            self.assertEqual(p["difficulty"], "Hard")
            self.assertEqual(len(p["kinds"]), 12)
            self.assertEqual(len(p["station_types"]), 24)
            self.assertEqual(len(design["tasks"]), 36)
            self.assertEqual(design["material_selection"]["animal"], [])
            self.assertEqual(len(design["material_selection"]["geographic"]), 8)
            self.assertEqual(len(design["material_selection"]["human"]), 4)
            stages = [s for t in design["tasks"].values() for s in t["stages"]]
            from memorybenchmark.prototypes.station_composition import requirements

            self.assertEqual(
                set(
                    Counter(
                        (s["required_kind"], r) for s in stages for r in requirements(s)
                    ).values()
                ),
                {4},
            )
            counts = Counter(s["target"] for s in stages)
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
            self.assertEqual(
                design["evaluation"]["authoring_geometry_check"][
                    "unused_strict_replicas"
                ],
                [],
            )
            self.assertEqual(
                len({(v["x"], v["y"]) for v in p["locations"].values()}),
                len(p["locations"]),
            )
            assignment = design["private_worlds"][map_world(design)]
            self.assertEqual(len(assignment), 48)
            for kind in p["kinds"]:
                matches = {
                    r: {
                        t
                        for t, v in design["private_station_capabilities"].items()
                        if kind in v[r]
                    }
                    for r in p["requirements"]
                }
                self.assertTrue(all(len(v) == 2 for v in matches.values()))
                self.assertNotEqual(matches["catalogue"], matches["verify"])
                self.assertFalse(
                    matches["catalogue"] & matches["verify"],
                    "A correct type must never bypass the processing requirement",
                )

    def test_every_composition_has_both_earlier_standalone_experiences(self):
        from memorybenchmark.prototypes.station_composition import requirements

        for design in self.designs.values():
            prior = set()
            combined = 0
            for task in design["tasks"].values():
                fresh = set()
                for stage in task["stages"]:
                    operations = requirements(stage)
                    if len(operations) == 2:
                        combined += 1
                        self.assertTrue(
                            {(stage["required_kind"], r) for r in operations} <= prior
                        )
                    else:
                        fresh.add((stage["required_kind"], operations[0]))
                prior.update(fresh)
            self.assertEqual(combined, 24)

    def test_individual_geographies_match_installed_graphs_and_real_crossings(self):
        from scripts.hard_geography import geography
        from scripts.hard_geography.review import review

        signatures = []
        for theme, design in self.designs.items():
            authored = geography(theme)
            checked = review(authored)
            self.assertEqual(design["public"]["locations"], authored["locations"])
            self.assertEqual(design["public"]["edges"], authored["edges"])
            self.assertEqual(design["public"]["view_box"], authored["view_box"])
            self.assertFalse(checked["unconnected_visual_crossings"], theme)
            self.assertFalse(checked["unapproved_barrier_crossings"], theme)
            self.assertGreater(checked["minimum_station_separation"], 180)
            self.assertGreaterEqual(
                checked["minimum_point_separation"],
                95,
                "Every clickable road/site marker needs visible separation",
            )
            stats = checked["topology"]
            self.assertTrue(stats["connected"])
            self.assertGreater(stats["station_degree_histogram"].get(2, 0), 3)
            signatures.append(
                (
                    stats["cycle_rank"],
                    tuple(stats["core_branch_degree_histogram"].items()),
                    tuple(stats["station_degree_histogram"].items()),
                )
            )
        self.assertEqual(
            len(set(signatures)),
            3,
            "Hard maps must have distinct route structure, beyond terrain colours",
        )

    def test_river_bridges_and_moat_gates_have_different_structural_roles(self):
        from scripts.hard_geography import geography

        def components_without_crossings(geo):
            adj = {n: set() for n in geo["locations"]}
            for a, b, _ in geo["edges"]:
                tags = set(geo["edge_tags"]["|".join(sorted((a, b)))])
                if tags & {"bridge", "causeway"}:
                    continue
                adj[a].add(b)
                adj[b].add(a)
            unseen = set(adj)
            groups = []
            while unseen:
                todo = [min(unseen)]
                found = set()
                while todo:
                    n = todo.pop()
                    if n in found:
                        continue
                    found.add(n)
                    todo.extend(adj[n] - found)
                unseen -= found
                groups.append(found)
            return groups

        orcia, hampi, angkor = (geography(t) for t in ("orcia", "hampi", "angkor"))
        self.assertEqual(
            len(components_without_crossings(orcia)),
            2,
            "Three separated bridges connect the two valley banks",
        )
        self.assertEqual(
            len(components_without_crossings(hampi)),
            1,
            "The Hampi network stays on one river bank",
        )
        self.assertEqual(
            len(components_without_crossings(angkor)),
            3,
            "City, southern enclosure and exterior use separate causeways",
        )

    def test_same_material_changes_result_with_explicit_requirement(self):
        design, station, kind = self.pair()
        game = StationGame(map_world(design), design)
        session = StationSession(game, "T1", feedback_mode="compact")
        self.collect(game)
        walk(game, station)
        result = session.dispatch(
            {
                "command": "action",
                "request_id": "catalogue",
                "action": {"type": "process"},
            }
        )
        self.assertEqual(result["feedback"]["result"], "processed")
        self.assertEqual(result["feedback"]["requirement"], "catalogue")
        self.assertIn("归档编目", result["text"])
        self.assertNotIn("verify", result["feedback"]["capability"])
        game.step({"type": "abandon"})
        session = StationSession(game, "T2", feedback_mode="compact")
        self.collect(game)
        walk(game, station)
        before = game.steps
        request = {
            "command": "action",
            "request_id": "verify",
            "action": {"type": "process"},
        }
        result = session.dispatch(request)
        self.assertEqual(result["feedback"]["result"], "unsupported")
        self.assertTrue(game.state.raw)
        self.assertFalse(game.state.processed)
        self.assertIn("关联核验", result["text"])
        self.assertEqual(result, session.dispatch(request))
        self.assertEqual(game.steps, before + 1)
        self.assertEqual(
            session.dispatch(
                {
                    "command": "action",
                    "request_id": "override",
                    "action": {"type": "process", "requirement": "catalogue"},
                }
            )["error"],
            "invalid_request",
        )

    def test_type_transfer_requires_the_same_requirement(self):
        design, station, kind = self.pair()
        game = StationGame(map_world(design), design)
        StationSession(game, "T1")
        self.collect(game)
        walk(game, station)
        game.step({"type": "process"})
        support = evidence_support(design, game.events)
        counterpart = next(
            s
            for s in design["public"]["station_types"][station[0]]["stations"]
            if s != station
        )
        self.assertEqual(
            historical_status(design, support, counterpart, kind, "catalogue"),
            "known_match",
        )
        self.assertEqual(
            historical_status(design, support, counterpart, kind, "verify"),
            "unresolved",
        )
        with self.assertRaises(ValueError):
            historical_status(design, support, counterpart, kind)
        feedback = next(
            e["delivered"]["feedback"]
            for e in game.events
            if e.get("delivered", {}).get("feedback", {}).get("kind")
            == "station_information"
        )
        different = deepcopy(feedback)
        different["requirement"] = "verify"
        different["capability"] = design["private_worlds"][map_world(design)][station][
            "verify"
        ]
        evidence_support(
            design,
            [
                {"delivered": {"feedback": feedback}},
                {"delivered": {"feedback": different}},
            ],
        )
        invalid = deepcopy(feedback)
        invalid["capability"] = ["not_the_same_fact"]
        with self.assertRaisesRegex(ValueError, "contradict"):
            evidence_support(
                design,
                [
                    {"delivered": {"feedback": feedback}},
                    {"delivered": {"feedback": invalid}},
                ],
            )
        missing = deepcopy(feedback)
        missing.pop("requirement")
        with self.assertRaisesRegex(ValueError, "requirement"):
            evidence_support(design, [{"delivered": {"feedback": missing}}])

    def test_scoring_and_opportunities_do_not_import_other_requirement(self):
        design, station, kind = self.pair()
        game = StationGame(map_world(design), design)
        StationSession(game, "T1")
        self.collect(game)
        walk(game, station)
        game.step({"type": "process"})
        walk(game, "C")
        game.step({"type": "submit"})
        StationSession(game, "T2")
        self.collect(game)
        walk(game, station)
        game.step({"type": "process"})
        opportunity = experience_opportunities(design, game.events, game.task_run_id)[
            "stages"
        ][0]
        self.assertFalse(opportunity["has_prior_matching_opportunity"])
        self.assertEqual(len(opportunity["other_requirement_feedback"]), 1)
        self.assertEqual(opportunity["planned_predecessor_stages"], [])
        decisions = station_decisions(design, game.events, game.task_run_id)
        self.assertEqual(
            decisions["first_postcollection_station"]["pre_task_history"][
                "selected_historical_status"
            ],
            "unresolved",
        )
        game.step({"type": "abandon"})
        score = score_stream(design, game.events, condition="retain")
        self.assertFalse(score["stages"][1]["historical_matching_opportunity"])
        self.assertFalse(score["stages"][1]["direct_matching_evidence"])
        self.assertFalse(score["stages"][1]["new_target_for_previously_required_kind"])
        self.assertEqual(
            [r["correct"] for r in score["processing_attempts"]], [True, False]
        )
        self.assertEqual(
            [r["requirement"] for r in score["processing_attempts"]],
            ["catalogue", "verify"],
        )

    def test_invalid_requirement_and_modified_fixture_are_rejected(self):
        original = self.designs["orcia"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design.json"
            for change in ("requirement", "fixture"):
                design = deepcopy(original)
                if change == "requirement":
                    design["tasks"]["T1"]["stages"][1]["requirement"] = "unknown"
                else:
                    design["private_worlds"][map_world(design)]["A1"]["verify"] = [
                        "unknown"
                    ]
                path.write_text(json.dumps(design), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_design(path)

    def test_native_budget_and_anonymous_current_task(self):
        from memorybenchmark.prototypes.station_independent import initialize
        from memorybenchmark.prototypes.station_pilot import StationNativeSessions

        with patch("memorybenchmark.agent_sessions.require_mcp"):
            for agent in ("ga", "hermes"):
                sessions = StationNativeSessions(
                    Path("source"),
                    Path("support"),
                    None,
                    agent=agent,
                    model_alias="fixture",
                    max_turns=400,
                    final_turns=6,
                )
                self.assertEqual(sessions.max_turns, 400)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "native.tar"
            archive.write_bytes(b"fixture")
            adapter = Mock()
            adapter.prepare.side_effect = lambda archive, output: (
                output / "baseline"
            ).mkdir()
            with patch(
                "memorybenchmark.prototypes.station_independent.load_adapter",
                return_value=adapter,
            ):
                report = initialize(
                    root / "run",
                    archive,
                    agent="ga",
                    condition="clear",
                    design_path=station_design("hampi-hard"),
                )
            self.assertEqual(report["max_turns"], 400)
            self.assertEqual(len(report["tasks"]), 36)
            self.assertEqual(report["transport_retries"], 0)
            self.assertEqual(report["transport_failure_limit"], 0)
            self.assertEqual(report["reasoning_effort"], "high")
        for design in self.designs.values():
            game = StationGame(map_world(design), design)
            initial = StationSession(game, "T1", feedback_mode="compact").initial
            self.assertIn(
                design["public"]["requirements"][game.task["requirement"]],
                initial["text"],
            )
            text = json.dumps(initial, ensure_ascii=False).lower()
            for token in (
                "private_world",
                "private_station",
                "provenance",
                "https://",
                "orcia",
                "hampi",
                "angkor",
                "奥尔恰",
                "亨比",
                "吴哥",
                "bbox",
            ):
                self.assertNotIn(token, text)

    def test_http_human_names_and_condition_aware_design(self):
        with tempfile.TemporaryDirectory() as folder:
            server = make_server(port=0, log_root=Path(folder))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                expected = {
                    "capulin-easy": "卡普林火山",
                    "forest-easy": "缪尔森林",
                    "cascade-easy": "普利维特采湖区",
                    "orcia-hard": "奥尔恰谷",
                    "hampi-hard": "亨比",
                    "angkor-hard": "吴哥",
                }
                for key, name in expected.items():
                    with urlopen(
                        Request(
                            base + "/api/field/start?map=" + key,
                            data=b"{}",
                            headers={"Content-Type": "application/json"},
                        )
                    ) as response:
                        initial = json.load(response)
                    self.assertEqual(initial["display_name"], name)
                    self.assertEqual(
                        initial["observation"]["environment"]["name"],
                        load_design(station_design(key))["public"]["name"],
                    )
                    if key.endswith("hard"):
                        self.assertIn(
                            initial["observation"]["task"]["requirement"],
                            ("catalogue", "verify"),
                        )
                        with urlopen(
                            base
                            + "/api/field/design?map="
                            + key
                            + "&instance_id="
                            + initial["instance_id"]
                        ) as response:
                            detail = json.load(response)
                        self.assertEqual(detail["name"], name)
                        self.assertEqual(len(detail["triggers"]), 48)
                        first = detail["tasks"][0]["stage_options"][0]
                        self.assertEqual(len(first["matching_stations"]), 4)
                        terrain = initial["observation"]["environment"]["terrain"]
                        with urlopen(base + "/" + terrain + "-terrain.svg") as response:
                            self.assertIn("<svg", response.read().decode())
            finally:
                server.shutdown()
                server.server_close()
                thread.join()

    def test_public_route_cache_does_not_read_or_cache_private_truth(self):
        original = self.designs["orcia"]
        variant = deepcopy(original)
        variant["private_worlds"] = {}
        variant["private_station_capabilities"] = {}
        self.assertEqual(
            shortest_route(original, "C", "A1"), shortest_route(variant, "C", "A1")
        )
        path, cost = shortest_route(original, "C", "A1")
        path.clear()
        self.assertTrue(shortest_route(original, "C", "A1")[0])

    def test_real_mcp_delivers_only_the_active_requirement(self):
        from importlib.metadata import version, PackageNotFoundError
        from memorybenchmark.mcp_game import MCPGameClient, SDK_VERSION
        from memorybenchmark.prototypes.station_pilot import movement_tool

        try:
            installed = version("mcp")
        except PackageNotFoundError:
            installed = None
        if installed != SDK_VERSION:
            self.skipTest("Pinned MCP SDK extra unavailable")
        design, station, kind = self.pair()
        game = StationGame(map_world(design), design)
        session = StationSession(game, "T1", feedback_mode="compact")
        self.collect(game)
        walk(game, station)
        request = {
            "command": "action",
            "request_id": "mcp-conditional",
            "action": {"type": "process"},
        }
        with MCPGameClient(
            session.dispatch,
            definition=movement_tool("step", design),
            target_actions=("move",),
        ) as client:
            response = client(request)
            before = game.steps
            repeated = client(request)
        self.assertEqual(response, repeated)
        self.assertEqual(game.steps, before)
        self.assertEqual(response["feedback"]["requirement"], "catalogue")
        self.assertEqual(
            response["feedback"]["capability"],
            design["private_worlds"][map_world(design)][station]["catalogue"],
        )
        self.assertNotIn("private", json.dumps(response))


if __name__ == "__main__":
    unittest.main()
