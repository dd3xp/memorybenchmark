"""Validated server-owned runtime configuration, separate from experiment inputs."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    project: Path
    private_root: Path
    native_archive: Path
    native_runtime: str
    runtime_dependencies: tuple[str, ...]
    python: Path
    distro: str = "Ubuntu"
    recovery_interval_minutes: int = 5
    minimum_free_gib: int = 8

    @classmethod
    def load(cls, path):
        values = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if values.get("schema") != "benchmark-runtime-1":
            raise ValueError("Unsupported experiment runtime configuration")
        if values.get("enabled") is not True:
            raise ValueError("Experiment creation is disabled in server configuration")
        result = cls(
            project=Path(values["project"]),
            private_root=Path(values["private_root"]),
            native_archive=Path(values["native_archive"]),
            native_runtime=values["native_runtime"],
            runtime_dependencies=tuple(values["runtime_dependencies"]),
            python=Path(values["python"]),
            distro=values.get("distro", "Ubuntu"),
            recovery_interval_minutes=values.get("recovery_interval_minutes", 5),
            minimum_free_gib=values.get("minimum_free_gib", 8),
        )
        if not 1 <= result.recovery_interval_minutes <= 60:
            raise ValueError("Recovery interval must be 1–60 minutes")
        if result.minimum_free_gib < 2:
            raise ValueError("Storage reserve must be at least 2 GiB")
        return result

    @property
    def experiments(self):
        return self.private_root / "experiments"

    def gateways(self):
        return json.loads(
            (self.project / "config/model-gateways.json").read_text(
                encoding="utf-8-sig"
            )
        )
