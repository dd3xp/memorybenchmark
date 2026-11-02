# 独立实验运行

当前站点实验采用 `station-independent-experiment-1`。一个 run 只包含一个 agent、一个记忆条件和完整的 20 项任务。保留组和清除组分别从 T1 开始，各有自己的目录、实验 ID、原生基础库、游戏历史、进度表、进程、所有权锁、错误与重试预算。

两组共用固定地图定义、任务顺序、原生 agent 版本、模型与预算。每组只继承自己的已完成任务：保留组载入自己上一任务输出的记忆，清除组每个任务载入该 run 最初的原生基础库。清除组产生的本轮记忆仍完整保存供审计，但不传给下一任务。两组的历史对话、工作记忆和临时文件均不跨 session 传递。

两组不读取对方的进度、环境检查点、记忆或结果。没有任务对齐屏障；一组可运行 T8，另一组仍在 T3。一组中断、恢复、完成或审计，不影响另一组。比较只在两组结束后离线进行。

## 启动与恢复

各自在单独进程中启动以下命令，输出目录必须不同。Hermes 的运行时还需要原有的 `--runtime-dependency` 参数。

```powershell
python -m memorybenchmark.prototypes.station_independent --archive native-agent.tar.gz --agent ga --condition retain --output .runs/pilot-ga-retain --base-url https://gateway.example --runtime /path/to/native-runtime
python -m memorybenchmark.prototypes.station_independent --archive native-agent.tar.gz --agent ga --condition clear --output .runs/pilot-ga-clear --base-url https://gateway.example --runtime /path/to/native-runtime
```

凭据只通过宿主环境变量 `MEMORYBENCH_GATEWAY_KEY` 提供。`--prepare-only` 可先冻结独立 run，之后单独 `--resume`。原生 GA 仍使用 `code_run` 调用游戏客户端，Hermes 仍通过原生 MCP；一次模型响应最多一个游戏动作，移动只到一个相邻地点。提示、原生记忆机制、地图和动作反馈保持原样。

新 run 可用 `--reasoning-effort high` 指定推理强度，未指定则沿用 `low`。该字段同时冻结在实验清单、每个任务和实际模型请求中；宿主在发送前核对原生请求，离线审计再次核对。恢复不能改变该设置，比较程序拒绝混合 high／low 两组。旧清单缺少字段时按原先的 low 处理。网页对 high 运行单独标记，完整报告记录提供方返回的 token 使用量、覆盖率与任务耗时；同一档推理强度不代表实际 token 相等。

强度约束适用于游戏决策和记忆复盘。Hermes 原生会话命名请求明确关闭推理，当前会话的原生上下文压缩可省略推理字段。按固定提示、角色和无工具结构分别识别为 `session_title`、`context_compression`，保留原生请求，仍计入调用预算和总 token；其他请求继续严格校验，不将跨 session 记忆整理归为上下文压缩。压缩识别覆盖固定原生版本的首次摘要（`TURNS TO SUMMARIZE`）和迭代更新（更新摘要的固定开头、`PREVIOUS SUMMARY`、`NEW TURNS TO INCORPORATE` 同时存在）两种形式。原生源码不修改。

对已经冻结的轮次修正宿主误拒绝时，保留原源码和已完成任务。先严格重放已完成轨迹、核对记忆输入和实际被拒请求，再将失败目录归档，恢复原任务起点。追加 `host_validation_repairs`，声明原版本、宿主覆盖版本、文件指纹、适用任务和验证证据；新代码副本与恢复程序一同归档，不悄悄改写原冻结清单。报告单列宿主误拒绝所耗模型调用，不混入有效任务成本。运行中的另一组不被打断。

Hermes 的原生后台复盘必须完成后才能结算并快照记忆。等待使用本 worker 的原有总时限，已用时间不清零；不额外设置比整项任务预算更短的 100 秒收尾上限。复盘调用仍计入原 main／final 调用预算，宿主与隔离进程仍执行原总时限。若修正已冻结轮次的等待缺陷，原支持文件保留，新增支持目录及其全部指纹单独记录、验证和归档。

```powershell
python -m memorybenchmark.prototypes.station_independent --resume --output .runs/pilot-ga-clear --base-url https://gateway.example --runtime /path/to/native-runtime
python -m scripts.report_station_experiment --run .runs/pilot-ga-clear --output clear-result.json
python -m scripts.compare_station_experiments --retain .runs/pilot-ga-retain --clear .runs/pilot-ga-clear --output comparison.json
```

源码审计逐文件核验执行时的 SHA-256、冻结副本和声明的 Git 版本。新 run 记录源码换行格式，报告入口自动沿用；较早的 Windows 冻结快照需在报告命令显式加 `--source-newlines crlf`。这只指定 Git 导出时的 LF→CRLF 转换，不放宽源码内容校验，也不修改原始运行记录。已完成任务的报告或归档失败可离线恢复，无需重启 agent。

支持文件审计遵循各原生适配器实际准备的文件集合：GA 校验五个公共文件，Hermes 另校验其专用 worker；所有已执行的支持文件必须存在且与冻结源码哈希相同。完整项目源码指纹中出现另一 agent 的模块，不代表当前 agent 必须部署或执行它。

所有权锁仅属于当前 run；操作系统在进程退出后释放。恢复先核验本 run 的冻结源码、原始基础库、输入记忆、原生隔离、动作反馈、轨迹图与模型记录。已完成游戏失败也是有效任务，不重跑；已识别传输故障最多再试两次，整轮最多归档八次传输失败，恢复不重置计数。未知或不完整记录保留并停止当前 run。

网页对每个独立 run 只生成一个运行项，进度为 20 项，不再从一份进度表伪装出两个实验。两个条件的结果和审计各自生成。离线比较同时报告成功数、全任务代价和双方成功的后续任务代价；T1 单列无历史对照。独立轨迹的经验获取机会允许不同，因此此设计测量完整记忆策略的长期效果，逐任务差值不再固定相同的已获经验。

## 历史数据

旧版 `station-native-pilot-1` 和 `station-paired-parallel-1` 保留为历史配对协议，详见 [旧协议](PAIRED_PARALLEL.md)。不能把旧清除探针重新标记为独立任务流；新设计使用新 ID、全新原生基础库重新运行。

## 验证

回归测试覆盖各自历史、清除组原始基础库、记忆链、独立进度、某组卡住时另一组继续完成、独立故障与恢复、重试预算跨恢复保留、重复所有者拒绝，以及旧配对数据拒绝冒充新协议。

`scripts.check_station_independent` 使用脚本响应运行两条完整的真实原生两任务实验，核查空上下文、记忆继承／清除、所有会话独立和自身历史重放；让保留组 T2 等待清除组整轮完成，以验证没有任务屏障。这是软件验证，不作为 agent 能力成绩。

[软件验证记录](assets/independent-experiments/validation.json)：本地／Squishy 各 222 项回归通过，两种原生 agent 各运行两条两任务实验，记忆继承与重置、自身历史重放、无任务屏障和独立离线比较均通过；真实模型调用为零。

[正式启动验证](assets/independent-experiments/live-validation.json)：GA／Hermes 各两轮 20 项实验已分别启动，四个独立后台进程均收到真实模型响应并执行游戏操作。公开页面显示四个不同实验 ID；此记录仅证明启动与隔离，不包含整轮能力成绩。
