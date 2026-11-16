"""Application service for reviewing and creating matched retain/clear pairs."""

import json
from hashlib import sha256
from pathlib import Path
import shutil
from uuid import uuid4

from ..map_catalog import MAPS, map_detail, station_design
from ..model_context import context_configuration
from ..watch import atomic_json
from .freezer import freeze
from .repository import PairRepository, exclusive, utc


class ExperimentService:
    def __init__(self, config, scheduler, *, maps=None, conditions=("retain", "clear")):
        self.config = config
        self.scheduler = scheduler
        self.maps = MAPS if maps is None else dict(maps)
        self.conditions = tuple(conditions)
        if self.conditions not in (("retain", "clear"), ("retain",), ("clear",)):
            raise ValueError(
                "Configure a pair or an explicitly selected single condition"
            )
        self.repository = PairRepository(config.experiments)

    def design_path(self, name):
        root = (self.config.project / "memorybenchmark/data").resolve()
        path = (root / self.maps[name][2]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Registered map escaped the server-owned data directory")
        return path

    def map_info(self, name):
        if name in MAPS and self.maps[name] == MAPS[name]:
            return map_detail(name)
        design = json.loads(self.design_path(name).read_text(encoding="utf-8-sig"))
        return {
            "name": self.maps[name][0],
            "difficulty": design["public"]["difficulty"],
            "task_count": len(design["tasks"]),
            "version": design["design_id"],
        }

    def options(self):
        registry = self.config.gateways()
        return {
            "models": [
                {"id": name, "context_tokens": row["hermes_context_tokens"]}
                for name, row in registry["models"].items()
            ],
            "maps": [
                {
                    "id": name,
                    **{
                        k: self.map_info(name)[k]
                        for k in ("name", "difficulty", "task_count", "version")
                    },
                }
                for name in self.maps
            ],
            "conditions": list(self.conditions),
            "agent": "hermes",
            "movement_modes": [
                {"id": "step", "name": "单步移动"},
                {"id": "route", "name": "连续移动（最多32步）"},
            ],
        }

    def preview(self, request):
        allowed = {"model", "map", "movement_mode", "request_id"}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError("Only model, map and movement mode can be selected")
        model, map_id = request.get("model"), request.get("map")
        if not isinstance(model, str) or model not in self.config.gateways()["models"]:
            raise ValueError("请选择已配置的模型。")
        if not isinstance(map_id, str) or map_id not in self.maps:
            raise ValueError("请选择有效地图。")
        mode = request.get("movement_mode", "step")
        if mode not in ("step", "route"):
            raise ValueError("请选择有效移动方式。")
        design = json.loads(self.design_path(map_id).read_text(encoding="utf-8-sig"))
        if design["public"]["difficulty"] == "Hard" and mode != "step":
            raise ValueError("本轮Hard实验固定使用单步移动。")
        context = context_configuration(
            model, self.config.project / "config/model-gateways.json"
        )
        budget = design["native_session_budget"]
        return {
            "model": model,
            "map": map_id,
            "map_name": self.maps[map_id][0],
            "design_id": design["design_id"],
            "movement_mode": mode,
            "action_policy": "batch" if mode == "route" else "single",
            "context_tokens": context["model_context_length"],
            "registry_sha256": context["registry_sha256"],
            "reasoning_effort": "high",
            "conditions": list(self.conditions),
            "tasks_per_condition": len(design["tasks"]),
            "total_tasks": len(self.conditions) * len(design["tasks"]),
            "main_model_calls": budget["main_model_calls"],
            "final_model_calls": 6,
            "game_steps": next(iter(design["tasks"].values()))["max_steps"],
            "effective_wall_seconds": 604800,
            "infrastructure_wait_seconds": 604800,
            "agent": "hermes",
        }

    def create(self, request):
        return self._create(request, dispatch=True)

    def prepare(self, request):
        """Freeze the server-selected specs for zero-model checks before dispatch."""
        return self._create(request, dispatch=False)

    def _create(self, request, *, dispatch):
        review = self.preview(request)
        pair_id = self.repository.pair_id(request.get("request_id"))
        selection = {key: review[key] for key in ("model", "map", "movement_mode")}
        with exclusive(self.repository.root / "creation.lock"):
            existing = self.repository.read(pair_id)
            if existing:
                if (
                    existing["selection"] != selection
                    or existing.get("review", {}).get("conditions", ["retain", "clear"])
                    != review["conditions"]
                ):
                    raise ValueError(
                        "Request ID was already used for a different experiment"
                    )
                return self.public_pair(
                    self._dispatch(existing) if dispatch else existing
                )
            if (
                shutil.disk_usage(self.config.private_root).free
                < self.config.minimum_free_gib * 2**30
            ):
                raise ValueError("磁盘空间不足，请先清理已归档实验。")
            pair_root = self.repository.pair_directory(pair_id)
            if pair_root.exists():
                # No pair record means dispatch was never reached. Only this
                # request's generated, unlaunched draft can be regenerated.
                if pair_root.is_symlink() or not pair_root.resolve().is_relative_to(
                    self.repository.root.resolve()
                ):
                    raise ValueError(
                        "Unlaunched draft escaped the experiment directory"
                    )
                if any(pair_root.rglob("pilot.json")):
                    raise ValueError("Unregistered scientific data needs diagnosis")
                shutil.rmtree(pair_root)
            pair_root.mkdir(parents=True, exist_ok=False)
            jobs = []
            for condition in self.conditions:
                root = pair_root / condition
                source_digest = freeze(
                    self.config.project,
                    root / "runtime-hermes",
                    self.maps[review["map"]][2],
                )
                job = {
                    "schema": "benchmark-job-1",
                    "id": uuid4().hex,
                    "pair_id": pair_id,
                    "root": str(root),
                    "condition": condition,
                    **review,
                    "design_file": self.maps[review["map"]][2],
                    "source_digest": source_digest,
                    "native_archive": str(self.config.native_archive),
                    "native_runtime": self.config.native_runtime,
                    "runtime_dependencies": list(self.config.runtime_dependencies),
                    "distro": self.config.distro,
                    "python": str(self.config.python),
                    "minimum_free_gib": self.config.minimum_free_gib,
                    "created_at": utc(),
                }
                atomic_json(root / "job.json", job)
                jobs.append(job)
            if len({job["source_digest"] for job in jobs}) != 1:
                raise ValueError(
                    "Source changed while preparing the pair; nothing dispatched"
                )
            pair = {
                "id": pair_id,
                "created_at": utc(),
                "selection": selection,
                "review": review,
                "jobs": jobs,
                "phase": "prepared",
            }
            self.repository.save(pair_id, pair)
            # Every selected immutable spec exists before any science starts.
            return self.public_pair(self._dispatch(pair) if dispatch else pair)

    def _dispatch(self, pair):
        if pair["phase"] == "dispatched":
            return pair
        for job in pair["jobs"]:
            if job["id"] in pair.get("dispatched_jobs", []):
                continue
            self.scheduler.dispatch(job, self.config)
            pair.setdefault("dispatched_jobs", []).append(job["id"])
            self.repository.save(pair["id"], pair)
        pair["phase"] = "dispatched"
        self.repository.save(pair["id"], pair)
        return pair

    @staticmethod
    def public_pair(pair):
        return {
            "id": pair["id"],
            "phase": pair["phase"],
            "created_at": pair["created_at"],
            "review": pair["review"],
            "jobs": [
                {"id": job["id"], "condition": job["condition"]} for job in pair["jobs"]
            ],
        }

    def listing(self):
        return [
            {
                **row,
                "map_name": self.maps[row["map"]][0],
                "comparison_key": sha256(row["id"].encode()).hexdigest()[:16],
            }
            for row in self.repository.listing()
        ]
