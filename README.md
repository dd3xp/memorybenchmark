# Memorybenchmark：制图游戏原型

同一个规则核心供人类和 Agent 操作。当前实现小地图、两项测绘任务、文字动作接口、浏览器界面、完整事件日志和基础轨迹诊断。研究设计见 [实验设计](EXPERIMENT_DESIGN.md)，模块职责见 [软件架构](GAME_SOFTWARE_ARCHITECTURE.md)。

## 人类游玩

需要 Python 3.10 或更高版本，运行时无需第三方依赖。在仓库根目录执行：

```powershell
python -m memorybenchmark
```

打开 <http://127.0.0.1:8765>，点击“开始探索”。选择通路移动，在任务地点“测量地点”，然后“提交测绘”。第一项任务结束后可以接第二项任务。地图只显示当前任务已发现的局部地理信息；操作推进游戏时间，思考和界面等待不推进。

这是机制原型：勘测点使用抽象坐标，测量暂用一个动作完成；天气使用评测侧不规则预设时间表；尚未实现完整工具系统、真实地形和四档难度。人类界面会记录本任务已发现的地理内容，Agent 也收到同样的公开地图信息；新任务清空这份临时地图。

## Agent 文字接口

当前提供的是可接入原生 Agent 的环境传输接口，**还没有完成 GenericAgent 和 Hermes 的实际工具注册、状态隔离及记忆对照运行**。GA 在本项目指 GenericAgent。

### JSON Lines

```powershell
python -m memorybenchmark --stdio
```

每行输入一个 JSON 对象，每行得到一个响应：

```json
{"command":"start","task_id":"T1"}
{"command":"action","request_id":"move-1","expected_revision":1,"action":{"type":"move","target":"J"}}
{"command":"read"}
```

`expected_revision` 使用上一响应的 `observation.revision`。重复发送完全相同的动作请求及 `request_id` 返回原响应，不重复移动；同一编号对应不同参数或过期的状态版本会返回协议错误。原型允许省略版本，正式工具桥应发送该字段。动作有 `move(target)`、`observe`、`survey`、`wait`、`submit`、`abandon`。

`read` 读取已公开的观察，不推进时间；`observe` 是一次显式观察动作。不能移动的相邻通路仍可尝试，环境不会提前用隐藏通行规则过滤选项。文字工具和图形界面均通过 `GameAdapter` 调用规则核心。

### HTTP

同一个本地服务提供：

- `POST /api/start`：`{"task_id":"T1"}` 创建独立实例，响应含 `instance_id`。任务结束后携带这个标识开始下一任务，评测历史继续保留，公开任务状态重置。
- `POST /api/action`：提交 `instance_id`、`request_id`、`expected_revision` 和 `action`。
- `GET /api/observation?instance_id=...`：读取当前公开观察。

服务仅绑定本机回环地址。事件日志和隐藏规则不通过 HTTP 提供。真实 Agent 应在独立执行环境运行，只能接触接口和自己的记忆空间；当前 Web/stdio 演示本身没有建立该进程隔离。

## 轨迹校准与测试

```powershell
python -m unittest discover -s tests -v
python -m memorybenchmark.calibrate
```

校准程序用同一段合法历史构造两条手工行为轨迹。两者都完成第二项任务、移动 5 次、距离 8；一条返回路径包含首次到达的新地点，另一条包含对已有明确负反馈通路的再次尝试。输出位于 `.runs/calibration/`，包括完整 JSONL 和 `comparison.json`。

这些是评测器的校准样例，不是真实 Agent 的记忆效果或新颖性验证。当前分析描述“返回过程中包含新地点／重复受阻”；未判断探索是否有净收益，也未把符合经验的行动等同于内部调用记忆。尚未实现完整四维指标、任务要求复查等语境判定、提前绕行机会识别或原生记忆干预。

运行记录位于 `.runs/<实例编号>/events.jsonl`。每次实际移动生成独立有序边，重复移动不合并；原地失败、测量、等待保留为事件。实际交付的完整观察另存于每个事件的 `delivered`，不截断。

```powershell
python -m memorybenchmark --analyze .runs/calibration/repeated_block.jsonl
```

日志仅供评测侧访问，不能放进被测 Agent 的可读目录。下一步将按原生适配边界接入 Hermes 和 GenericAgent，匹配任务提示与反思机会，验证保留／清除自主记忆的对照。
