# 尼斯湖水怪

第一张正式 Easy 地图，地图标识 `nessie-easy`，规则版本 `nessie-easy-1.1`。包含 61 个地点、61 条道路、8 个测绘点、8 种站型、16 座基站和 20 项双段测绘委托。原有八类资料和二十项委托完整保留，只有 H 型的两座基站采用水怪研究主题；原生 Hermes 的保留／清除两条独立校准任务流已启动，完整效果待跑完后报告。

![完整公开地图](assets/nessie-easy/complete-map.svg)

配置：[nessie_easy20.json](../memorybenchmark/data/nessie_easy20.json)。旧岚汀丘地图及全部冻结实验保留，不能把两张地图的成绩混算。

## 地形与命名

保留尼斯湖西南—东北的狭长湖盆、两条岸侧通路及林地支路作为骨架。西岸山岭与东岸林地的地景依据来自 [BGS Invermoriston 地质说明](https://webapps.bgs.ac.uk/Memoirs/docs/B01912.html)、[Forestry and Land Scotland 的大峡谷林地](https://forestryandland.gov.scot/visit/forests-by-region/forests-in-the-great-glen)与 [Farigaig 林地步道](https://forestryandland.gov.scot/visit/destinations/farigaig)。

湖体、林地和等高纹理为自行绘制的地形示意。地点名称、营地、基站、道路、距离和功能配对均为游戏设计，不对应现实设施或徒步路线。地图标题使用“尼斯湖水怪”，节点名称仍虚构；现实地名和研究来源不进入 Agent 的地图或任务。

H1、H2 命名为“H 型水怪勘测站”，其余七型使用测绘基站名称。研究主题只用于站点命名；H 型仍从原有测绘资料中匹配处理一种，实际能力由现场反馈获知。游戏继续围绕地理测绘展开，委托的目标、资料种类、先后顺序和交付规则与原测绘策划完全一致。

两岸只在湖的两端连接，湖面没有横穿道路。主路构成一个环，基站分布在支路末端；全部中间节点需要真实移动。地图和基础距离从 T1 起公开，自由探索，不按任务锁区。

## 跨 session 需要复用的经验

任务要求采集并处理指定测绘资料。公开信息包含候选能力和站型位置；具体“站型 → 支持哪类资料”通过现场 `inspect` 或 `process` 得到。

| 公开站网 | 站型 | 候选资料 | 同型实例 |
| --- | --- | --- | --- |
| 南北同型站网 | A、B、C、D | 剖面、岸线、植被、岩性 | 每型两座，分别分布于湖的北端和南端 |
| 东西同型站网 | E、F、G、H | 方位、高程、水系、等高线 | 每型两座，分别分布于西岸和东岸 |

同型一致与各站网内的一一对应关系是公开规则，字母不暗示功能。配对是地图的固定属性，所有 Agent、记忆条件、重复实验与人类游玩完全一致；候选世界仅供评测器区分未知事实与已获得的信息，不作运行时随机分配。

到目标自动采集本段资料；匹配处理后进入下一段；两段完成后只能回 C 营地交付。错误处理保留资料并反馈实际能力，查询和处理各消耗一次操作。当前段资料、位置、对话与工作记忆在任务边界重置，只有 Agent 自主管理的持久记忆跨 session。公共地理图不附送旧能力反馈。

前序整项失败不抹去已经交付的经验，也不补发没有经历过的经验。评测记录实际反馈来源、同型传播、逻辑推断、首次支路选择、当场重新查询及通勤成本。

## 二十项委托

每项从 C 出发，按顺序完成两段后回 C 交付一次。八种测绘资料各出现五次，40 段中 32 段有更早的同类处理需求。T1、T2 都是普通任务，首次需求仍可受此前自由探索影响。任务流不随 Agent 的选择或失败改写。

| 委托 | 第 1 段 | 第 2 段 |
| --- | --- | --- |
| T1 联程巡测 01 | P 剖面 | R 方位 |
| T2 联程巡测 02 | U 植被 | X 水系 |
| T3 联程巡测 03 | Q 剖面 | V 植被 |
| T4 联程巡测 04 | S 方位 | Y 水系 |
| T5 联程巡测 05 | P 岸线 | R 高程 |
| T6 联程巡测 06 | U 岩性 | X 等高线 |
| T7 联程巡测 07 | Q 岸线 | V 岩性 |
| T8 联程巡测 08 | S 高程 | Y 等高线 |
| T9 联程巡测 09 | Q 剖面 | V 植被 |
| T10 联程巡测 10 | S 方位 | Y 水系 |
| T11 联程巡测 11 | Q 岸线 | V 岩性 |
| T12 联程巡测 12 | S 高程 | Y 等高线 |
| T13 联程巡测 13 | U 剖面 | R 水系 |
| T14 联程巡测 14 | X 方位 | P 植被 |
| T15 联程巡测 15 | V 岸线 | S 等高线 |
| T16 联程巡测 16 | Y 高程 | Q 岩性 |
| T17 联程巡测 17 | U 剖面 | R 等高线 |
| T18 联程巡测 18 | X 方位 | P 岩性 |
| T19 联程巡测 19 | U 岸线 | R 水系 |
| T20 联程巡测 20 | X 高程 | P 植被 |

T9–T12 是四项完整行程的重复；T13–T20 将已有需求换到其他调查点并重新组合。匹配站不由委托指定，Agent 可以在两个同型实例中选择，也可以自由查询其他站。完整来源计划见[逐段经验前序](assets/nessie-easy/task-dependencies.json)；实际可用经验仍以该 Agent 已收到的反馈为准。

## 游玩、设计查看与接入

- `/maps?id=nessie-easy`：完整公开地图，可开启经验点标记。
- `/play?map=nessie-easy`：点击相邻节点移动，采集、查询、处理与回营交付。
- `/play?map=nessie-easy&inspect=1`：显式人类设计查看，包含真实配对、全部任务和经验来源；不改变进度，不进入 Agent 观察。

游玩页默认打开新图；`/easy20` 与旧地图链接继续打开原型。人类和 Agent 使用同一个 `StationGame`、`StationSession` 和现有 MCP 通路，无需修改 GA／Hermes 的原生工具或记忆。

```powershell
python -m memorybenchmark.prototypes.station_session --design memorybenchmark/data/nessie_easy20.json --human --all-tasks
python -m scripts.build_nessie_easy_map
python -m scripts.render_nessie_easy --output docs/assets/nessie-easy
python -m scripts.check_nessie_easy --output .runs/nessie-validation-new
python -m unittest tests.test_nessie_easy -v
```

原生独立运行器继续使用 `memorybenchmark.prototypes.station_independent`，传入 `--design memorybenchmark/data/nessie_easy20.json`。保留／清除组各自独立运行完整 20 项，T1 单列；操作预算 88，原生主循环 100 次调用、同 session 收尾 6 次、总时限 3,600 秒。新图启用时从各 Agent 的原始基础记忆开始。

## 校验

规则版本 1.1 已部署 Squishy。本地 250 项回归通过（8 项因环境跳过），服务器 20 项新图与实验观测专项检查全部通过、无跳过；包含与原测绘策划逐项比较的检查，确认八类资料和二十项委托完全一致，只有一种站型带有水怪主题。

公网 HTTPS 完成 T1、T2 两项测绘委托，确认剖面、方位、植被和水系资料正常采集处理，水怪主题站同样按原规则处理测绘资料。真实浏览器显示“联程巡测 01：采集剖面资料”，并仅有 H1/H2 两座水怪主题站。新图 MCP、原鉴权、任务间重置及操作幂等通过，旧实验索引与冻结清单未变。[当前部署与游玩验收](assets/nessie-easy/deployment-validation.json)。

此前将全图误改为水怪调查的 1.0 版验收单独保留在[历史记录](assets/nessie-easy/history/nessie-easy-1.0/deployment-validation.json)，不作为当前设计的验收。

[软件与信息结构校验](assets/nessie-easy/validation.json)穷举 165,888 组兼容站型顺序，并把各项最坏情况在真实规则内核重放；该策略最坏 85 次操作。576 个候选配对下的两种反馈策略共 23,040 次模拟完成，实际固定配对另做 40 次真实内核重放，覆盖完整保留和清除流程。

这些是规则可行性与信息价值校验，模型调用为零；不能当作 GA／Hermes 的记忆收益或路线 GT。八种固定配对用于 Easy 的获取与复用实验，容量和长期干扰需另设条件。

## 记忆收益校验与真实 Agent 校准

[受控反馈策略校验](assets/nessie-easy/memory-value/memory-value.json)固定同一条根据公开地理选站的策略，只改变是否保留此前实际交付的站点反馈。当前地图 T2–T20 的保留／清除路程为 968／1330，少走 27.22%；操作为 610／900，少 32.22%；选站尝试为 39／87。19 项中 18 项路程更短、1 项相同；T1 无历史时两组完全相同。

同一策略检查全部 576 种候选配对，T1–T20 总路程均有正收益，降幅范围为 22.21%–31.54%；实际运行仍使用同一固定配对。该校验验证图中存在可利用的经验价值，未给原生 Agent 注入这些脚本事实，也不表示任意 Agent 必然实现该比例。

另在真实规则内核重放两条各自独立的前十三项任务流，导出 T13 的[保留历史轨迹](assets/nessie-easy/memory-value/cases/T13-scripted-retain.svg)与[清除历史轨迹](assets/nessie-easy/memory-value/cases/T13-scripted-clear.svg)，路程分别为 64／98。边和节点操作来自实际重放，完整事件以无损 gzip 保存；这是脚本轨迹，不是 Hermes 成绩。

```powershell
python -m scripts.audit_nessie_memory_value --output .runs/nessie-memory-value-check
```

Hermes 真实校准沿用原生版本 `e5ea5fd`、Luna、原生 high、单步动作与 100／6 次调用及 3,600 秒预算，冻结执行源码 `124d734`。保留和清除分别执行完整 20 项，各自有基础记忆、上下文、实际历史、进度、恢复、审计和归档；比较只在两组独立结束后进行，T1 单列。没有导入旧地图经验，没有依据真实成绩修改地图、任务、提示词或 Agent 记忆实现。

[启动核查](assets/nessie-easy/native-memory-launch.json)确认两组各 87 个来源文件、真实模型响应与原生 MCP 游戏动作，网页各显示一个独立实验。[T1→T2 实际边界核查](assets/nessie-easy/native-memory-boundary.json)确认两组首两项均成功，保留组 T2 输入清单匹配自己的 T1 输出，清除组 T2 匹配原始基础库，且 T2 的历史对话、后台历史与工作记忆均为空。[实际模型输入核查](assets/nessie-easy/native-memory-delivery.json)进一步验证保留组 T1 自写 MEMORY 正文完整进入 T2 首次请求，清除组自己的上一任务 MEMORY 正文未进入请求；只发布来源指纹与匹配计数。完整真实收益以最终审计对照结果为准。
