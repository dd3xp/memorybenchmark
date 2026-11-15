"""Windows scheduler adapter; web requests never supply executable commands."""

import os
import subprocess


class WindowsScheduler:
    def dispatch(self, job, config):
        if os.name != "nt":
            raise RuntimeError(
                "Configure a supported scheduler before launching experiments"
            )
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(config.project / "scripts/register_experiment.ps1"),
                "-JobFile",
                str(__import__("pathlib").Path(job["root"]) / "job.json"),
                "-IntervalMinutes",
                str(config.recovery_interval_minutes),
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            # Credentials are read inside the task, never passed through this process.
            raise RuntimeError(
                "Experiment task registration failed; inspect server scheduler logs"
            )
