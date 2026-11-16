# Benchmark experiment defaults

- The user explicitly requires every experiment to run as a retain/clear pair (2026-11-08). A request to run a model/map means both memory conditions, unless the user explicitly requests a single condition. Never interpret it as retain only.
- Before dispatch, check that both conditions are in the plan for every authorized model/map. If one condition already exists, preserve it and launch only the missing counterpart. Do not rerun completed tasks or import retain learning into clear.
- Keep model, map, task sequence, original baseline and scientific budgets matched within each pair. Each condition owns its own root, history, memory, attempts, costs and archive.
- This default does not authorize additional models/maps or resurrect withdrawn experiments. Preserve existing authorization boundaries and failure evidence.

# Verified model context configuration

- Use `config/model-gateways.json` for model context and gateway routes. Never hardcode a shared64k window or guess a model's limit. Keep official model capacity, the account route's default/optional maximum, and gateway throughput limits as separate fields.
- Freeze the selected registry with each new experiment; verify the worker's actual context receipt before claiming startup. Unknown models must stop for configuration instead of falling back to64k. Existing completed results keep their original recorded settings.
- The 2026-11-15 user correction supersedes all earlier retention exceptions: all 64000-context experiment results are invalid, including old Gemini cohorts and the four former Luna single-step controls. Remove their scientific data/archives and never use their scores as baselines. Preserve current 250000/272000-context runs, shared dependencies and reusable deployment code. Frozen active executors remain byte-exact; old metadata embedded in their provenance is not a valid result or control. Lunatic stays deferred.

# Experiment storage and retention

- Follow `config/evidence-storage.json` for every new experiment package. Freeze the repaired event store, model-audit reader, working-memory lifecycle and native-source cache with the executor. Do not reuse an old executor ZIP that restores full-history-per-task duplication.
- Keep cumulative game history in the run's immutable compressed event blocks; session snapshots reference those blocks. Keep model request parameters once, with SHA-checked audit references. Preserve original responses, signatures, failure attempts and unknown usage.
- Share only verified immutable native source by archive hash. Retain and clear baselines, working memories and checkpoints must remain independent copies. Retire a task's temporary working copy only after committing and verifying its checkpoint; preserve failed or uncommitted state.
- Closing an experiment includes a retention decision: after a complete archive is verified, remove only proven unpacked duplicates with a separate recovery receipt. Keep at least one complete verified archive, scientific summaries, public projections, costs and unique evidence. Do not retain archive plus every unpacked duplicate indefinitely.
- Exclude all current experiment roots and shared dependencies from historical cleanup. Never hot-patch or restart a frozen worker for storage cleanup. Do not delete unique unarchived evidence; cold filesystem compression may reclaim space without changing logical bytes.

# Current implementation and unattended runs

- Hard36 uses two independent stages and typed processing; `config/hard36.json` and the per-map assessments define the reviewed allocation. Do not restore Hard48 as the current map. Historical tiny configs remain only as compatibility fixtures.
- The authorized new batch is exactly six Hermes/gpt-5.6-luna jobs: Orcia Hard36 step pair, Capulin Easy route pair, Nessie Normal route pair. All old64k single-step references are invalidated; there is currently no valid existing control, and no additional runs are authorized. Persisted in `config/authorized-launch-20261115.json`.
- Subsequent explicit user authorization (2026-11-15, America/New_York): autonomous Hard design iteration includes actual model calibration, at most two rounds, each retain/clear pair of12 tasks (48 tasks total), using native Hermes/gpt-5.6-luna, step movement,272000 context and the original400+6/352 budgets. This overrides the preceding no-additional-runs restriction only for this bounded calibration. See `config/authorized-hard-calibration.json`. Preserve every attempt; do not change existing runs or promote a candidate merely because a diagnostic program separates it from Normal.
- Use the managed experiment service and its server-owned runtime configuration. No dated prepare/launch copies or Codex monitoring automation. Preserve same-RPC request recovery, S4U boot recovery, strict checkpoint adoption, final audit and verified retention. Unknown failures pause rather than blindly replaying real game failures.
- Follow `docs/CODE_STYLE.md`: separate domain, persistence, scheduling, transport and HTTP, use injected adapters and behavioral tests, keep configuration explicit, avoid speculative abstractions.

# UI conventions

- Avoid unnecessary secondary labels and descriptions. Let the layout do the explaining. This is an explicit user preference (2026-11-15).
- Put experiment creation beside the experiment list and open it in a modal, preserving the current page and selection. Keep the basic form short; disclose fixed budgets only on demand.
- Show a visible accessible loading indicator while data is pending. Distinguish loading, empty results and errors; never display an empty-state message before loading finishes. Respect reduced motion and preserve keyboard focus.
