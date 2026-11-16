# 第二版Hard完整保留组确认

2026-11-16用户明确要求“跑完整的看看，只跑有记忆的”。此次新增授权仅为一个36项retain流，覆盖默认成对要求；不启动clear，也不重跑已封存的两轮校准。

- 模型与执行器：Hermes／gpt-5.6-luna，原生primary high、单步、272000上下文。
- 世界：预先保留的61501，`candidates/orcia_binding36.json`；保持既有道路、站点和采集点。
- 委托：24项普通双段＋12项双组合，共36项、72独立阶段、96次必需处理。相关经验来自此前正常计分委托。
- 初始记忆：独立原始baseline，不导入校准或其他实验学习；每个新任务只继承本组自己的记忆。
- 预算：每项400主调用＋6收尾、352游戏步、一周有效wall与独立一周基础设施等待。原同RPC／相同请求字节恢复、S4U开机接续、严格checkpoint和原最终审计／归档保持有效。

[授权配置](../config/authorized-hard-binding36-retain.json)固定唯一请求ID `hard-binding36-retain-61501-v1`，对应group `090bc79375b93118d7a77ae19244d8fe`。托管入口为`python -m scripts.run_hard_confirmation --runtime-config <server-owned-config>`，只允许这一个完整retain确认；重复请求幂等，不会生成clear。浏览器默认创建仍为retain／clear成对，不能从请求参数覆盖服务端条件。

科学配置在派发前冻结；先检查选定设计SHA、预算、上下文及零模型原生探针，再校验原始baseline的331文件清单SHA。运行由托管服务独立推进，不依赖Codex监控或SSH连接。未知错误暂停并保留现场，真实游戏失败不盲目重跑。

此任务是对[两轮校准](HARD_CALIBRATION_RESULTS.md)筛出的候选作完整确认。启动不代表36项已经成功，也不把12项校准结果扩写成完整成绩；未替换公共实验创建菜单的正式Hard地图。实际启动与模型证据记录在本地`.runs/hard-binding36-confirmation/`及远程本group的原始receipts。
