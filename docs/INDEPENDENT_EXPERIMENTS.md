# 独立实验运行

当前站点实验采用 `station-independent-experiment-1`。一个 run 只包含一个 agent、一个记忆条件和完整任务流：Easy 为 20 项，Normal 为 30 项。保留组和清除组分别从 T1 开始，各有自己的目录、实验 ID、原生基础库、游戏历史、进度表、进程、所有权锁、错误与重试预算。默认地图为 `rainbow-easy`，其他地图通过 `--design` 显式选择。

两组共用固定地图定义、任务顺序、原生 agent 版本、模型与预算。每组只继承自己的已完成任务：保留组载入自己上一任务输出的记忆，清除组每个任务载入该 run 最初的原生基础库。清除组产生的本轮记忆仍完整保存供审计，但不传给下一任务。两组的历史对话、工作记忆和临时文件均不跨 session 传递。

两组不读取对方的进度、环境检查点、记忆或结果。没有任务对齐屏障；一组可运行 T8，另一组仍在 T3。一组中断、恢复、完成或审计，不影响另一组。比较只在两组结束后离线进行。

## 启动与恢复

各自在单独进程中启动以下命令，输出目录必须不同。Hermes 的运行时还需要原有的 `--runtime-dependency` 参数。

```powershell
python -m memorybenchmark.prototypes.station_independent --archive native-agent.tar.gz --agent ga --condition retain --output .runs/pilot-ga-retain --base-url https://gateway.example --runtime /path/to/native-runtime
python -m memorybenchmark.prototypes.station_independent --archive native-agent.tar.gz --agent ga --condition clear --output .runs/pilot-ga-clear --base-url https://gateway.example --runtime /path/to/native-runtime
```

凭据只通过宿主环境变量 `MEMORYBENCH_GATEWAY_KEY` 提供。`--prepare-only` 可先冻结独立 run，之后单独 `--resume`。原生 GA 仍使用 `code_run` 调用游戏客户端，Hermes 仍通过原生 MCP；一次模型响应最多一个游戏动作，移动只到一个相邻地点。提示、原生记忆机制、地图和动作反馈保持原样。

新 run 可用 `--reasoning-effort high` 指定推理强度，未指定则沿用 `low`。GA 通过其原生 `mykey.py` 的 `native_oai_config.reasoning_effort` 加载，Hermes 通过原生 `AIAgent(reasoning_config={"effort": "high"})` 加载，由各自上游代码生成实际请求。实验清单与任务记录冻结的是这个 agent 配置；恢复不能改变它，比较程序拒绝混合 high／low 两组。旧清单缺少字段时按原先的 low 处理。网页对 high 运行单独标记，完整报告记录提供方返回的 token 使用量、覆盖率与任务耗时；同一档推理强度不代表实际 token 相等。

运行器不根据逐请求的推理字段拦截、补写或覆盖原生请求，归档也不要求每个请求／提供方响应与主 agent 的配置相同。Hermes 原生后台复盘、会话命名与上下文压缩的具体推理设置遵循上游流程。`session_title`、`context_compression` 等分类只用于统计，未来未知的辅助形式也不会被拒绝。报告分别列出配置档位、实际请求档位分布和提供方返回档位分布；未提供字段记为 `unspecified`，不推断为 low 或 high。原生源码不修改。

对已经冻结的轮次修正宿主误拒绝时，保留原源码和已完成任务。先严格重放已完成轨迹、核对记忆输入和实际被拒请求，再将失败目录归档，恢复原任务起点。追加 `host_validation_repairs`，声明原版本、宿主覆盖版本、文件指纹、适用任务和验证证据；新代码副本与恢复程序一同归档，不悄悄改写原冻结清单。报告单列宿主误拒绝所耗模型调用，不混入有效任务成本。运行中的另一组不被打断。

Hermes 的原生后台复盘必须完成后才能结算并快照记忆。等待使用本 worker 的原有总时限，已用时间不清零；不额外设置比整项任务预算更短的 100 秒收尾上限。复盘调用仍计入原 main／final 调用预算，宿主与隔离进程仍执行原总时限。若修正已冻结轮次的等待缺陷，原支持文件保留，新增支持目录及其全部指纹单独记录、验证和归档。

```powershell
python -m memorybenchmark.prototypes.station_independent --resume --output .runs/pilot-ga-clear --base-url https://gateway.example --runtime /path/to/native-runtime
python -m scripts.report_station_experiment --run .runs/pilot-ga-clear --output clear-result.json
python -m scripts.compare_station_experiments --retain .runs/pilot-ga-retain --clear .runs/pilot-ga-clear --output comparison.json
```

源码审计逐文件核验执行时的 SHA-256、冻结副本和声明的 Git 版本。新 run 记录源码换行格式，报告入口自动沿用；较早的 Windows 冻结快照需在报告命令显式加 `--source-newlines crlf`。这只指定 Git 导出时的 LF→CRLF 转换，不放宽源码内容校验，也不修改原始运行记录。已完成任务的报告或归档失败可离线恢复，无需重启 agent。

支持文件审计遵循各原生适配器实际准备的文件集合：GA 校验五个公共文件，Hermes 另校验其专用 worker；所有已执行的支持文件必须存在且与冻结源码哈希相同。完整项目源码指纹中出现另一 agent 的模块，不代表当前 agent 必须部署或执行它。

所有权锁仅属于当前 run；操作系统在进程退出后释放。恢复先核验本 run 的冻结源码、原始基础库、输入记忆、原生隔离、动作反馈、轨迹图与模型记录。已完成游戏失败也是有效任务，不重跑。未知或不完整记录保留并停止当前 run。

当前独立运行入口使用 `same-request-recovery-1`：暂时性网络错误和 HTTP 408／425／429／5xx 在同一模型 RPC 内重试，保持同一个原生 worker、上下文、工作记忆和已执行游戏动作。每次重试发送完全相同的请求字节；只在收到完整响应后向原生 agent 交付一次。物理请求单独记入每任务的 `transport-attempts.jsonl`，不重复增加逻辑模型调用和游戏动作。采用指数退避，通常最长间隔五分钟，并遵循提供方 `Retry-After`；每任务累计基础设施等待最多一周，失败次数不作为终止条件。401／403、无效请求、证书错误、不可恢复的模型响应及响应体超限进入待修复状态。

任务的原有模型调用预算与有效运行时限保持不变。失败请求及退避等待不消耗任务时限，成功请求的耗时正常计入。宿主每秒更新只含计时信息的租约，外部进程守护按有效运行时间和一周故障等待上限执行终止；宿主失联九十秒会清理隔离进程。agent 仍看不到凭据、评测器或历史上下文，原生代码与它自己的工具、记忆流程不修改。进程真正死亡后只能从已验证的任务边界恢复，不能假称原生会话已恢复。

Hermes 自身的请求、首字节和流停滞 watchdog 通过上游支持的 `HERMES_API_TIMEOUT`、`HERMES_API_CALL_STALE_TIMEOUT`、`HERMES_STREAM_STALE_TIMEOUT` 及 `HERMES_CODEX_*_TIMEOUT_SECONDS` 配齐宿主恢复窗口，避免外层继续重试、原生内部先超时。实际环境配置写入任务的 `request_recovery.native_transport_environment`。这不改变推理档位、工具、记忆行为或主／收尾调用预算。

原生 `providers.custom.request_timeout_seconds`／`stale_timeout_seconds` 与 `auxiliary.<task>.timeout`／`no_progress_timeout` 同步设置网络等待上限。冻结轮次通过仅作用于宿主生成的 Hermes 配置的兼容层应用，不修改上游代码，也不重写原生模型请求。旧覆盖版本、驱动、清单和安装任务边界一起归档。

旧版每任务重跑次数和整组失败次数仍保留在历史清单中，用于解释旧数据；普通网关故障现在由请求层处理，不再依靠整任务重跑。对已冻结轮次安装恢复覆盖时，原源文件和已完成记录保持原样，保存原驱动与清单、覆盖代码哈希、安装边界和验证记录并一起归档。失败尝试消耗的 token 计入基础设施成本；提供方没有报告的用量记为未知。

网页对每个独立 run 只生成一个运行项，进度为 20 项，不再从一份进度表伪装出两个实验。两个条件的结果和审计各自生成。离线比较同时报告成功数、全任务代价和双方成功的后续任务代价；T1 单列无历史对照。独立轨迹的经验获取机会允许不同，因此此设计测量完整记忆策略的长期效果，逐任务差值不再固定相同的已获经验。

## 历史数据

旧版 `station-native-pilot-1` 和 `station-paired-parallel-1` 保留为历史配对协议，详见 [旧协议](history/PAIRED_PARALLEL.md)。不能把旧清除探针重新标记为独立任务流；新设计使用新 ID、全新原生基础库重新运行。

## 验证

请求恢复验证使用真实原生 GA／Hermes 和模拟 SSE，真实网关调用为零。两端各注入两次 55 秒故障后，同一请求、同一 worker、已执行移动和原生记忆写入均保持；有效任务时钟分别只计正常执行时间。Hermes 对齐原生网络配置后另通过两次 70 秒故障，总计 140 秒，跨过其原生默认 120 秒首字节时限，仍在同一个 session 内完成。记录：[GA 110 秒](assets/request-recovery/ga-long-validation.json)、[Hermes 110 秒](assets/request-recovery/hermes-long-validation.json)、[Hermes 140 秒及原生配置](assets/request-recovery/hermes-watchdog-long-validation.json)。这些是故障恢复软件验证，不是记忆能力成绩。

回归测试覆盖各自历史、清除组原始基础库、记忆链、独立进度、某组卡住时另一组继续完成、独立故障与恢复、重试预算跨恢复保留、重复所有者拒绝，以及旧配对数据拒绝冒充新协议。

`scripts.check_station_independent` 使用脚本响应运行两条完整的真实原生两任务实验，核查空上下文、记忆继承／清除、所有会话独立和自身历史重放；让保留组 T2 等待清除组整轮完成，以验证没有任务屏障。这是软件验证，不作为 agent 能力成绩。

[软件验证记录](assets/independent-experiments/validation.json)：本地／Squishy 各 222 项回归通过，两种原生 agent 各运行两条两任务实验，记忆继承与重置、自身历史重放、无任务屏障和独立离线比较均通过；真实模型调用为零。

[正式启动验证](assets/independent-experiments/live-validation.json)：GA／Hermes 各两轮 20 项实验已分别启动，四个独立后台进程均收到真实模型响应并执行游戏操作。公开页面显示四个不同实验 ID；此记录仅证明启动与隔离，不包含整轮能力成绩。
