# Cartographer’s Notebook · 测绘手记

游戏与论文共用这一主标题，论文副标题后续确定。代码包与仓库名称为 `memorybenchmark`。

共享规则核心供人类和 Agent 操作。默认地图有 9 个地点、6 项连续委托，支持到达自动测绘、体力、风险与工具。研究目标是从轨迹分析 Agent 自主形成的跨 session 记忆对后续行为的作用。

- [实验设计](EXPERIMENT_DESIGN.md)：研究问题与评测边界。
- [经验目录](EXPERIENCE_CATALOG.md)：当前地点、风险、工具、任务与校准结果。
- [软件架构](GAME_SOFTWARE_ARCHITECTURE.md)：核心与两类适配器。
- [原生 Agent 适配](docs/AGENT_INTEGRATION.md)：GenericAgent／Hermes 工具桥和验证范围。
- [当前成果](PROGRESS.md)：已完成验证、真实开发试跑与下一步验收。
- [GA 跨 session 流程](docs/GA_CROSS_SESSION.md)：沿用 AAAI 版记忆边界，接入独立会话、检查点与配对干预。
- [Squishy 部署与网页观测](docs/SQUISHY_DEPLOYMENT.md)：服务端路径、启动方式、实时回放与端口映射。

## 开始游玩

Python 3.10+，游戏本身不需要第三方依赖。在仓库根目录：

```powershell
python -m memorybenchmark
```

打开 <http://127.0.0.1:8765> 查看实验观测台。实验运行时自动更新当前任务、Agent 已发现的地图、实际通勤、执行动态与记忆文件变化；选择已完成的会话可逐动作回放。网页只读观察实验，不会修改 Agent 的会话或记忆。

亲自游玩使用 <http://127.0.0.1:8765/play>，点击“开始探索”。选择道路，到达即记录地理信息。在工具点取用工具后会自动生效；到达目标后“提交记录”。任务结束后可继续下一委托，失败也能继续。

公网部署使用 PIN 登录：页面、静态资源和接口统一校验会话，支持退出登录、12 小时过期和错误尝试限速。私有配置只保存加盐哈希，PIN 不进入仓库。使用 `python -m memorybenchmark.web_auth .runs/web-auth.json` 在本机交互设置 PIN；服务启动时自动读取此文件，也可用 `--auth-file` 指定路径。生产 Cookie 要求 HTTPS；仅本地 HTTP 开发可加 `--local-http-cookie`。Squishy 的后台启动脚本缺少鉴权配置时会拒绝启动。

原生 HTTPS 使用 `--tls-cert <证书链.pem> --tls-key <私钥.pem>`，也可通过 `MEMORYBENCH_TLS_CERT` 和 `MEMORYBENCH_TLS_KEY` 配置。程序直接加载已有证书，每 60 秒检测续期并自动更新，更新不完整时保留上一份有效证书；启动时加载失败则拒绝运行。Sakura 仅需 TCP 转发并关闭“自动 HTTPS”。证书和私钥不放入仓库。

地图只显示本任务已发现的地理信息，危险标签不自动进入地图。任务边界清空临时图和携带工具，恢复任务配置体力。每个动作按规则推进世界时间，思考、渲染或模型调用不会推进。天气由不规则预设时间表决定；当前山谷和森林风险暂不依赖天气。

这是机制原型，尚没有真实地形、完整四档难度或真实 Agent 的受控记忆效果结果。

## 文字接口

```powershell
python -m memorybenchmark --stdio
```

每行一个 JSON 请求，每行一个响应：

```json
{"command":"start","task_id":"T1"}
{"command":"action","request_id":"move-1","expected_revision":1,"action":{"type":"move","target":"J"}}
{"command":"read"}
```

动作有 `move(target)`、`take(target)`、`observe`、`wait`、`submit` 和 `abandon`。独立 `survey` 动作已移除。`read` 读取已交付的当前观察，不替代收费的调查，也不推进时间。原型中观察、等待、取用和提交花费游戏时间但不消耗体力。

`expected_revision` 使用上一响应的版本；完全相同的动作请求和编号重发，不重复执行。改变同一请求的参数或使用过期版本会返回协议错误。原型允许省略版本，正式桥接应发送它。无路可走、遭遇风险、体力耗尽属于正常游戏反馈，与通信错误分别处理。

本地服务也提供 `POST /api/start`、`POST /api/action`、`GET /api/observation?instance_id=...`。开始请求返回实例编号；后续携带编号在同一运行中推进任务。服务只绑定回环地址，评测日志和完整地图不通过 HTTP 提供。

Agent 应使用单独执行环境，仅能接触游戏接口和自身记忆空间。`agent_bridge.py` 提供原生工具注册，本地 HTTP 演示本身没有建立文件／网络隔离。GA 的专用跨 session 运行器使用 WSL2 与 bubblewrap，支持从共同历史进行保留／清除干预；原生联调、运行方式与验证范围见跨 session 流程。

## 验证与分析

```powershell
python -m unittest discover -s tests -v
python -m memorybenchmark.calibrate
python -m memorybenchmark.tool_calibration
python -m memorybenchmark.validation
```

渡口校准保留旧场景，区分两条都成功、移动 5 次、距离 8 的轨迹；其文字环境可用 `--stdio --scenario river` 启动。新工具校准包含四种都成功的行为，体力需求分别为 10、18、12、26；输出在 `.runs/tool-calibration/`。

这些是人工行为校准，不能当作真实 Agent 的记忆效果或新颖性证据。静态求解器验证六项任务的可行性，明确使用全世界信息，不是未知世界 Agent 必须达到的记忆 GT；动态条件超出其范围时会拒绝求解。

每次移动生成一条独立有序通勤边；取用、原地受阻和等待保留为事件。边保留距离、体力需求、风险代价和携带状态。完整响应记录在 `delivered`，不截断；工具说明和风险反馈只在实际公开后登记证据。

```powershell
python -m memorybenchmark --analyze .runs/tool-calibration/belated_preparation.jsonl
```

日志只供评测侧访问。当前诊断描述返回结构、取用时机、已有证据与风险代价，不直接认定内部检索过某条记忆。GA 记忆干预通路可以运行；完整四维指标与正式能力实验仍待验证。
