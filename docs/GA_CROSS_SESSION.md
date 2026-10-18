# GA 跨 session 运行与对照

当前入口是 `python -m memorybenchmark.ga_experiment`。使用旧复现包中的原生 GenericAgent，类名保留其原始拼写 `GeneraticAgent`；没有用自写规划器替代 Agent。

新运行支持 [雾汀湖 Easy](EASY_LAKE.md) 的 T1–T8；命令行默认场景为 `lake-easy`，复现旧试跑时显式使用 `--scenario valley`。新实验冻结初始世界，记录共享地理协议。两组共享已提交的地点、连接和距离，清除经验记忆不清除公共地图；危险、工具位置与效果不写入地图。

## 与 AAAI 旧代码的对应

已核对本地旧版 `backend/src/agent/ga_wrapper.py`、`ga_daemon.py`、`_sandbox.py` 和 `backend/src/runner.py`：

| 旧版行为 | 本次继承与适配 |
| --- | --- |
| `reset()` / `_h_reset()` 清除 Agent history、backend history、handler 和压缩状态 | 每任务新进程、新原生对象和新 backend；记录空 history 和 working；临时目录也重新建立 |
| `clear_memory()` 从白板归档恢复整个 memory 目录 | 恢复同一份原版基础记忆目录，包括记忆管理 SOP；不把“清除”实现成空目录 |
| `backup_memory()` / `restore_memory()` 与任务检查点 | 只在进程退出后生成完整文件清单与快照；保存配套的世界快照；对照使用独立副本 |
| 原生 `do_start_long_term_update` 自主触发 | 保留原工具和记忆策略，不调用额外摘要器，不代写经验 |
| 任务末尾给 Agent 整理机会 | 保留相同功能，两组使用同一提示和相同独立轮数上限，包括任务失败 |
| daemon 与文件／网络隔离 | 使用独立原生 worker 和 WSL2 bubblewrap；游戏真值和模型凭据留在宿主运行器 |

旧 runner 在末轮给 MEM 提示提炼经验，给 NOMEM 提示直接停止。本次两组统一为“自行判断是否有值得保留的实际经历，可使用原生工具整理，也可结束”，避免把整理机会差异混入记忆干预。

之前的单任务开发脚本 `native_ga_smoke.py` 排除了整个 `memory/`，因此丢失了原生 L0 记忆管理 SOP。它保留为历史开发检查；跨 session 入口完整保留归档自带的基础能力。基础目录不包含本游戏的人工经验。

## 任务与对照如何推进

1. 公共历史先由真实 GA 执行前缀任务，使用其实际写出的记忆；失败也保留实际经历。
2. 在下一个任务开始前冻结世界与记忆。保留组恢复累积记忆，清除组恢复原版基础目录。
3. 两组启动独立新 session，使用相同公开任务、游戏初始状态、工具、提示和预算。后续任务描述不提前给 Agent。
4. 清除组是当前检查点上的一次反事实探测，其行为和新写内容不进入公共历史。保留组的实际结果推进历史，再为下一个任务生成新检查点。

这里的“前缀”只是已经发生的实际历史，不规定任务专门负责采集经验，也不保证它学会了哪些内容；每个后续任务仍可同时学习与复用，没有固定的采集／测试阶段。

这是逐任务的“相同实际历史下清除已有经验”干预，不是两条各自演化的完整 MEM/NOMEM 任务流。两种协议回答的问题不同，不能混报。Python 随机种子一致不等于网关模型输出确定；需要重复运行才能估计效果与不确定性。

## 隔离与持久化范围

- 只把原生源码、运行依赖和工具桥只读挂载给 Agent，唯一持久可写位置为 `/agent/memory`。
- `/agent/temp`、`/tmp` 和 HOME 都是每会话重新创建的临时空间。原生工作记忆、计划、临时脚本和模型历史不会自然跨会话保留。要保留的技能或经验由 Agent 放入自己的 memory 目录。
- Agent 无法访问 `/mnt/c`、宿主进程和网络。原生文件、脚本工具仍可操作隔离环境；没有真实浏览器或桌面。
- 游戏与模型调用通过 stdin/stdout 的限定消息交给父进程处理。Agent 无法新建游戏或选择未来任务。HTTPS 和真实凭据只在父进程中使用。
- 每个 session 做文件、网络和空上下文检查；使用无条件标签的随机宿主记忆路径，避免挂载信息泄露 retain/clear 名称。
- worker 退出、所在 PID namespace 结束后才快照；不允许软链接、特殊文件或过量记忆文件进入快照。隔离不可用时直接报错，没有退回未隔离模式。

每项任务有游戏操作预算、主循环模型调用上限和统一末轮整理上限。游戏操作预算耗尽／体力耗尽属于正常失败；模型轮数耗尽、自然结束但未完成会记录为运行器终止事件，不伪造 Agent 的 abandon 操作。基础设施错误保存部分记录，不算 Agent 成功或记忆失败。暂时的网关通信错误默认最多重试一次，每次同时恢复任务开始前的世界与记忆，成功的其他 session 不重跑；真实游戏失败不重试。

## 本地运行

Windows 需要 WSL2 Ubuntu 24.04、`bubblewrap`、Python 3.12 和专用运行依赖。游戏核心仍只需要标准库。WSL 内准备：

```bash
python3 -m venv ~/.local/share/memorybenchmark/runtime
~/.local/share/memorybenchmark/runtime/bin/python -m pip install requests beautifulsoup4 bottle simple-websocket-server
```

旧第三方源码归档不在公开仓库中，运行时由用户提供。无需模型调用的真实原生契约检查：

```powershell
python scripts/check_ga_sessions.py reproducibility_package_upload/agents/GenericAgent_src.tar.xz
```

该检查使用脚本化模型响应写入人工测试标记，验证真实原生工具、隔离和跨会话传递。**它不是自主记忆实验，也不是模型成绩。**

检查还会在一次清除组运行中制造通信错误和未提交的记忆写入，再恢复检查点：重复执行时世界回到原始起点，临时写入消失，已成功的前缀与保留组不会重跑。

真实模型运行要求在父进程环境中提供 `MEMORYBENCH_GATEWAY_KEY`：

```powershell
python -m memorybenchmark.ga_experiment reproducibility_package_upload/agents/GenericAgent_src.tar.xz --base-url https://your-gateway --scenario lake-easy --tasks T1 T2 T3 T4 T5 T6 T7 T8 --max-turns 48 --final-turns 6
```

默认发送 `max_output_tokens=2048`。当前使用的订阅网关明确返回“不支持该参数”；使用该路由需要显式加 `--max-output-tokens 0`，记录为网关默认输出长度。此时没有声称逐调用 token 硬上限，模型调用数、会话时间和接收字节上限仍有效。不自动静默移除参数。

中断后可以从原目录继续，保留冻结的 worker、原生版本、模型别名和预算；失败尝试另存，不覆盖：

```powershell
python -m memorybenchmark.ga_experiment --resume .runs/ga-cross-session/RUN_ID --base-url https://your-gateway
```

改变 Agent 工具桥或 worker 协议时应启动新运行，不能把不同协议悄悄拼成同一组。

模型协议保留原生 Responses 序列化和 SSE 解析，父进程仅限定目标、鉴权、预算和协议错误；完成事件处理参考 [OpenAI 官方流事件文档](https://developers.openai.com/api/reference/resources/responses/streaming-events)。网关别名不独立证明底层模型身份。

## 记录与解释

所有完整记录保存在忽略提交的 `.runs/ga-cross-session/<run-id>/`：原生归档 SHA、worker 与桥接 SHA、基础记忆清单、世界检查点、公开输入、原生工具调用、模型输入输出、通勤图与诊断。代码和文档可以公开；第三方源码、凭据、完整运行记录不随仓库提交。

`memory_changed` 包括工具读取产生的访问统计；`content_changed` 排除原生 `file_access_stats.json`，但仍只是内容变化，不自动证明记住了有效经验。工具日志能记录显式工具调用，不声称完整观察了每一次底层文件读取。

是否自主写入、是否出现可复用经验、是否有行为收益分别报告。单次小图联调用于验证协议，不发布四维能力分数或统计显著的记忆提升。
