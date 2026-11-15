# Experiments

## Start a matched pair

In the experiment list, click **新建实验**. Choose a model, map and movement mode in the modal, then click **启动实验**. Fixed budgets are under **运行设置**. The current page and experiment selection stay in place; `/experiments/new` remains a shortcut to the same modal. Every submission creates retain and clear together. The request ID makes a repeated HTTP submission idempotent. No page load, preview or status request calls a model. Existing PIN authentication and same-origin checks protect creation.

The server reads `config/experiment-runtime.json` (or `MEMORYBENCH_RUNTIME_CONFIG`). Copy the example, set server-owned paths and enable it. Credentials stay in the existing server DPAPI store or GeminiGateway connection file; they never enter browser input, frozen specs, source control or receipts. Unknown models fail instead of falling back to 64k. `config/model-gateways.json` separates model capacity, usable route context and throughput.

## Runtime ownership

`private/experiments/<pair-id>/{retain,clear}` owns independent job specs, memories, attempts, costs and results. `runtime-hermes/` freezes the executor, map, storage policy and context registry. Shared native source is verified by archive SHA; writable memories are never shared.

Each Windows task runs as the existing user using S4U, without an interactive desktop. Boot and five-minute triggers recover a killed host process; overlapping starts are refused by ownership locks. HTTP429, known 5xx and the exact tested subscription envelopes wait on the same worker/RPC/request bytes. Model-effective time excludes infrastructure waits; each has its own seven-day allowance. Unknown authentication or deterministic errors pause with a private diagnostic. Real game/budget failures are committed and never retried for score.

After a proven host reboot, preserve the interrupted attempt and its costs, restore only the run's own committed checkpoint (clear uses its original baseline), and continue missing tasks. Saved complete results undergo strict adoption, not replay. No Codex automation or external model watchdog is needed.

## Movement and interpretation

`step` moves across one adjacent edge per tool action. `route` accepts a chosen path of at most 32 adjacent moves in one Hermes game call; every edge still consumes its normal step and distance. It stops at invalid moves or terminal state. The host does not plan the path or perform hidden processing. Hard is fixed to `step` for the authorized batch. Cross-task retain/clear memory remains independent of movement mode.

Route runs freeze `action_policy=batch` so their submoves reach the host; step runs freeze `single`. Preparation, continuation, session receipts and peer audits use the same policy. A path schema alone does not establish multi-move execution. `scripts/check_hermes_route_host.py` drives the real Hermes/MCP/host with synthetic responses, verifies three moves from one response and feedback delivery, and makes zero provider calls. The four initial route starts with an incompatible single host gate were administratively superseded; their data and costs remain separate, and replacement pairs start from original baselines. Hard was not restarted.

The six-run launch is persisted in `config/authorized-launch-20261115.json`. All 64k historical cohorts, including the former single-step controls and old Gemini runs, were invalidated by the user on 2026-11-15. They are removed from the comparison registry and must not be used as baselines. The current six runs continue; no replacement control runs are implicitly authorized.

## Evidence lifecycle

Follow `config/evidence-storage.json`. Game history uses immutable compressed blocks and checked references, not full-history copies per task. Keep original requests/responses/signatures, physical failures, unknown usage, checkpoints and public summaries. The original final audit creates one verified ZIP. Only byte-proven unpacked model duplicates are retired after verification; `retention.json` gives exact recovery members. A reboot between verification and retention resumes retention alone. Tasks disable themselves only after both steps finish.

Use the ZIP for full raw inspection after closeout; keep pilot summaries, projection data, costs and the archive index online. Do not run duplicate finalizers. Do not download `.part`. Historical cleanup is an explicit contained deletion operation, separate from live workers.

For password-free reboot startup, run `scripts/save_task_credential.ps1` once on the server. It rewraps the existing subscription gateway token in machine-scope DPAPI with an explicit owner/SYSTEM/Administrators file ACL, never writes plaintext, and leaves the original user-scoped store unchanged. Scheduled jobs use this encrypted store; run it with `-Refresh` after deliberately rotating the gateway token. Gemini continues to use its original loopback gateway connection file.
