# Cartographer’s Notebook · 测绘手记

游戏与论文共用这一主标题，论文副标题后续确定。代码包与仓库名称为 `memorybenchmark`。

当前研究从**环境基本规则与信息结构**重新设计：先确定 Agent 能自主获得什么持久信息、信息怎样影响后续行动，再设计地图与委托，最后确定图分析与指标。岚汀丘地双站版已完成首轮真实 GA 试跑；四站巡测版已上线并通过机制校验，待运行真实 Agent。

共享规则核心供人类和 Agent 操作。网页和命令行默认进入 **雾汀湖 Easy**：31 个地点、31 条通路、3 个营地与 8 项委托，每项参考路线仅遇险 1–2 次。公开地图跨 session 点亮；现有原型围绕风险与工具经验产生行动差异，新版不默认沿用这一机制。

- [环境重设计范围](docs/ENVIRONMENT_REDESIGN.md)：当前已确认约束、开放规则与首份环境规格。
- [多项经验原型与试玩](docs/MULTI_EXPERIENCE_PROTOTYPE.md)：两组独立信息、部分知识、八项普通委托；288 条参考重放与 15 个真实 GA session 已完成。
- [首轮真实 GA 轨迹](reports/STATION_NATIVE_GA_PILOT.md)：自主保存、检索证据、提前停止，以及失败后的实际信息机会。
- [执行图与可测行为](reports/STATION_GRAPH_MEASUREMENT_PILOT.md)：实际参考成图、逐例描述量、图表示的必要信息及原生试跑故障记录。
- [首个可执行机制样例](docs/STATION_CAPABILITY_PROTOTYPE.md)：局部设施能力、两个匹配世界、参考搜索与真实交互图；已校验信息价值，未运行真实 Agent。
- [问题建模与解决方法](reports/记忆环境%20重设计%20问题建模.md)：多回合未知世界决策、匹配世界与机制校验的技术依据。
- [实验设计](EXPERIMENT_DESIGN.md)：最新研究边界与历史方案。
- [历史任务依赖候选](docs/TASK_DEPENDENCIES.md)：八项委托与结构校验记录，已降为历史候选，不作为下一版实施依据。
- [雾汀湖 Easy](docs/EASY_LAKE.md)：虚构命名、共享地理图、工具经验与八项轻量任务。
- [经验目录](EXPERIENCE_CATALOG.md)：当前地点、风险、工具、任务与校准结果。
- [软件架构](GAME_SOFTWARE_ARCHITECTURE.md)：核心与两类适配器。
- [统一 MCP 与 Agent 适配](docs/AGENT_INTEGRATION.md)：共用游戏服务、GA 完整适配、用户插件与验证范围。
- [当前成果](PROGRESS.md)：已完成验证、真实开发试跑与下一步验收。
- [GA 跨 session 流程](docs/GA_CROSS_SESSION.md)：沿用 AAAI 版记忆边界，接入独立会话、检查点与配对干预。
- [Squishy 部署与网页观测](docs/SQUISHY_DEPLOYMENT.md)：服务端路径、启动方式、实时回放与端口映射。

## 二十项 Easy 新地图

当前网页 `/easy20` 使用[四站巡测版](docs/EASY20_CHOICE_MAP.md)：38 地点、45 道路、8 个独立环路，每类资料有两个匹配站；最近站在匹配世界中一半正确、一半不正确，可以检查简单就近策略。二十项委托保留，新版机制校验已完成，真实 Agent 尚未重跑。

此前[岚汀丘地双站版](docs/EASY20_MAP.md) 的 22 地点、21 道路配置保留。它的首轮原生 GA 完成 20 项主线与 19 个清除记忆探针，全部成功、877 次模型调用；自主保存、行动前读取缺口和末项覆盖经验见[完整试跑与真实成图](reports/EASY20_NATIVE_GA_PILOT.md)。当前网页的“手记与地图”可检查四站新版完整设计与经验触发点。原雾汀湖继续在 `/play`。

## 开始游玩

Python 3.10+，游戏本身不需要第三方依赖。在仓库根目录：

```powershell
python -m memorybenchmark
```

打开 <http://127.0.0.1:8765> 查看实验观测台。实验运行时自动更新当前任务、Agent 已发现的地图、实际通勤、执行动态与记忆文件变化；选择已完成的会话可逐动作回放。网页只读观察实验，不会修改 Agent 的会话或记忆。

亲自游玩使用 <http://127.0.0.1:8765/play>，点击“开始探索”。直接点击地图上高亮的相邻地点前往，到达即记录地理信息；点击其他已发现地点只查看信息，不会自动寻路。放大后可以拖动地图，滚轮可缩放，“⌖”回到当前位置。工具到达取用点后才显示，取用后自动生效；本次到齐全部目标后，抵达指定营地才出现提交操作。背包、现场记录和菜单分别展开，支持 `I`／`J` 快捷键及 Tab、Enter／空格操作地图。同一标签页刷新可恢复服务器仍保留的游戏实例，服务重启后的实例失效会提示重新出发。

游玩页使用全屏俯视场景：湖岸、草地、树木、营地与路标组成环境，测绘员沿实际选择的单条通路行走；发现、遇险、取用与委托完成提供场景反馈。任务、体力与地点操作悬浮在场景上，`Esc` 打开菜单，可选开启音效或全屏。减少动态效果设置会跳过行走动画。画面只读取公开观察；装饰性植被与美术纹理不参与规则、轨迹或经验判定。地表纹理由内置 `image_gen` 生成，原始提示词与素材说明保存在 [scene_art.json](memorybenchmark/data/scene_art.json)。设计查看页和实验观测台继续提供图结构视图。

两类经验各有一次初次接触与三次后续应用机会，参考风险次数为 1、2、1、2、2、2、2、2；无对应工具遭遇两次必定耗尽体力。任务结束后可继续下一委托，失败也能继续。

Easy 体力耗尽时自动回本项出发营地复活，恢复体力并清空工具，本次测绘和经历保留；总操作预算不重置。trace 在致死移动之后追加死亡点到营地的复活边，默认权重 70，可由 `respawn.weight` 调整，网页显示为红色虚线。实际步行距离与复活惩罚分别统计，复活边不变成地图道路。最终成功也保留死亡代价，预算耗尽或主动结束才终止当前委托。

在探索菜单中点击“地图设计查看”，或访问 <http://127.0.0.1:8765/design>，查看地图全貌、风险／工具／准备位置和关联委托，可按任务切换并叠加参考路线。此页仅供人查看当前地图设计，不修改游戏进度或向 Agent 提供隐藏经验。

公网部署使用 PIN 登录：页面、静态资源和接口统一校验会话，登录有效期为 180 天，重启服务后继续有效；主动退出或更换 PIN 后撤销。私有配置保存 PIN 的加盐哈希，同目录的 `*.sessions.json` 只保存随机会话令牌的哈希与到期时间，不保存 PIN 或 Cookie 原文；两者都不进入仓库。使用 `python -m memorybenchmark.web_auth .runs/web-auth.json` 在本机交互设置 PIN；服务启动时自动读取此文件，也可用 `--auth-file` 指定路径。生产 Cookie 要求 HTTPS；仅本地 HTTP 开发可加 `--local-http-cookie`。错误尝试限速保留；Squishy 的后台启动脚本缺少鉴权配置时会拒绝启动。

原生 HTTPS 使用 `--tls-cert <证书链.pem> --tls-key <私钥.pem>`，也可通过 `MEMORYBENCH_TLS_CERT` 和 `MEMORYBENCH_TLS_KEY` 配置。程序直接加载已有证书，每 60 秒检测续期并自动更新，更新不完整时保留上一份有效证书；启动时加载失败则拒绝运行。Sakura 仅需 TCP 转发并关闭“自动 HTTPS”。证书和私钥不放入仓库。

Agent、人类和观测台都能看到成功提交后累计点亮的地理图，包含地点、连接和基础距离；危险、工具库存位置与应对经验不写进地图。两组干预获得相同公共地图，区别是 Agent 自主保存的经验记忆。每项任务仍须重新到达目标；任务边界清空本次到达记录和携带工具，在委托指定营地恢复体力。每个动作按规则推进世界时间，思考、渲染或模型调用不会推进；Easy 风险暂不随天气变化。

当前游戏使用虚构地名与中性场景标识 `lake-easy`，真实地理参考不进入任务、观察或界面。其余难度与真实 Agent 的受控记忆效果仍待校准。`--scenario valley` 保留 9 地点旧原型，`--scenario river` 保留渡口校准。

## 文字接口

支持 MCP 的 agent 可通过标准工具接口试玩固定委托。游戏核心仍无第三方依赖；安装可选接入依赖后：

```powershell
python -m pip install -e ".[mcp]"
python -m memorybenchmark.mcp_server --scenario lake-easy --task T1
```

服务仅公开当前任务的 `game_action`，先用 `read` 获得观察。stdout 属于 MCP；权威日志写入宿主 `.runs/mcp-play/`。此命令是单任务试玩，完整跨 session 评测还需要对应 agent 的生命周期适配器。

```powershell
python -m memorybenchmark.experiment --list-agents
python -m memorybenchmark.experiment path/to/GenericAgent_src.tar.xz --agent ga --base-url https://your-model-gateway --tasks T1 T2 T3 T4 T5 T6 T7 T8
```

GA 已经通过同一 MCP 服务接入公共运行器；旧 GA 入口继续兼容。新 agent 使用 `--adapter module:create_adapter` 提供插件；没有适配器时提前报配置错误，不产生零分或自动切换裸模型。当前只有 GA 完成全流程适配，Hermes 仍只有工具注册契约。运行条件、记忆边界与扩展方法见 [接入说明](docs/AGENT_INTEGRATION.md)。新运行在 `.runs/agent-cross-session/`，观测台同时兼容旧 GA 运行目录。

下面保留原有 JSON Lines 与 HTTP 开发接口：

```powershell
python -m memorybenchmark --stdio
```

每行一个 JSON 请求，每行一个响应：

```json
{"command":"start","task_id":"T1"}
{"command":"action","request_id":"move-1","expected_revision":1,"action":{"type":"move","target":"E1"}}
{"command":"read"}
```

动作有 `move(target)`、`take(target)`、`observe`、`wait`、`submit` 和 `abandon`。独立 `survey` 动作已移除。`read` 读取已交付的当前观察，不替代收费的调查，也不推进时间。原型中观察、等待、取用和提交花费游戏时间但不消耗体力。

`expected_revision` 使用上一响应的版本；完全相同的动作请求和编号重发，不重复执行。改变同一请求的参数或使用过期版本会返回协议错误。原型允许省略版本，正式桥接应发送它。无路可走、遭遇风险、体力耗尽属于正常游戏反馈，与通信错误分别处理。

本地服务也提供 `POST /api/start`、`POST /api/action`、`GET /api/observation?instance_id=...`。开始请求返回实例编号；后续携带编号在同一运行中推进任务。开始时可指定 `scenario: "lake-easy"`。`GET /api/atlas` 是已提交地理成果的独立读接口；Agent 从正常观察和文字结果获得同一共享地理信息。评测日志与尚未发现的完整地图不通过 HTTP 提供。

Agent 应使用单独执行环境，仅能接触游戏接口和自身记忆空间。`agent_bridge.py` 提供原生工具注册，本地 HTTP 演示本身没有建立文件／网络隔离。GA 的专用跨 session 运行器使用 WSL2 与 bubblewrap，支持从共同历史进行保留／清除干预；原生联调、运行方式与验证范围见跨 session 流程。

## 验证与分析

```powershell
python -m unittest discover -s tests -v
python -m memorybenchmark.calibrate
python -m memorybenchmark.tool_calibration
python -m memorybenchmark.validation
python -m memorybenchmark.validation --scenario lake-easy
python -m memorybenchmark.easy_calibration --output .runs/easy-calibration-new
```

可选浏览器验收需要 Node.js、Playwright 与 Chrome，不属于游戏运行依赖。先以 `python -m memorybenchmark --port 8875 --log-dir .runs/ui-review` 启动本地测试服务，再执行 `node scripts/check_play_ui.cjs http://127.0.0.1:8875`。检查真实地图点击、拖动防误触、键盘、请求丢失后的状态同步、取用工具、复活与营地提交，并在 `.runs/ui-review/screenshots/` 输出桌面与手机截图。第三个命令行参数可传入按任务编号组织的参考动作 JSON，通过真实界面重放全部委托；再追加 `pointer` 可改用鼠标点击重放。此脚本只创建人类游玩实例。

镜头专项验收执行 `node scripts/check_camera_ui.cjs http://127.0.0.1:8875`，覆盖全图拖动、边界反向拖动、鼠标位置缩放、视角保留、输入打断动画、响应返回时持续拖动，以及真实双指缩放／单指接续／取消和后续轻点。受保护的预览可通过环境变量 `MEMORYBENCH_UI_PIN` 提供登录 PIN。

人类界面在任意倍率下可拖动地图；滚轮围绕鼠标位置缩放，触屏支持双指缩放。拖动和滚轮进入自由查看，观察、等待或游戏响应不会强制归位；点击定位或按 `F` 回到角色并恢复跟随。`＋`／`−` 缩放，`Home` 查看全图，同标签页刷新保留当前镜头。音效偏好保存在本地。镜头与 HUD 均只改变人类展示，不生成游戏动作或额外公开经验。

渡口校准保留旧场景，区分两条都成功、移动 5 次、距离 8 的轨迹；其文字环境可用 `--stdio --scenario river` 启动。新工具校准包含四种都成功的行为，体力需求分别为 10、18、12、26；输出在 `.runs/tool-calibration/`。

这些是人工行为校准，不能当作真实 Agent 的记忆效果或新颖性证据。静态求解器验证六项任务的可行性，明确使用全世界信息，不是未知世界 Agent 必须达到的记忆 GT；动态条件超出其范围时会拒绝求解。

每次移动生成一条独立有序通勤边，自动复活另生成 `kind=respawn` 的加权边；取用、原地受阻和等待保留为事件。边保留顺序、生命序号、距离、体力需求、风险代价和携带状态。完整响应记录在 `delivered`，不截断；工具说明和风险反馈只在实际公开后登记证据。

```powershell
python -m memorybenchmark --analyze .runs/tool-calibration/belated_preparation.jsonl
```

日志只供评测侧访问。当前诊断描述返回结构、取用时机、已有证据与风险代价，不直接认定内部检索过某条记忆。GA 记忆干预通路可以运行；完整四维指标与正式能力实验仍待验证。
