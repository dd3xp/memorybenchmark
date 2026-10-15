# 可控操作、实际轨迹构图与自主跨 session 记忆：近邻文献审计

核查日：2026-10-15。范围为公开一手论文、论文附录及能定位的作者代码；不执行第三方代码，不把摘要命中当作全文核查，不承诺穷尽所有文献。用户的“任务约束”指环境的动作接口、前置条件和效果，而不是替 agent 指定正确执行计划。地图地点为节点，每次实际通勤为独立有向边，并保留顺序；正式被测记忆只能由 agent 的实际经历自主形成。

## 1. 是否已有“可控环境动作 → 实际执行轨迹 → 算法构图”的研究？

### Takeaway

有。EMG 与 Trajectory Graph Copilot 是明确、非常接近的轨迹直接构图先例，不能再用“其他图都靠 LLM 意义抽取”概括。MC-EvoBench 的图则是预先声明的任务—资源关系图，它与用户的实际通勤图不同。约束操作比开放代码任务更容易形成可靠执行表示，是方法适配优势，但“有限动作环境有状态图”本身不构成新发现。

### Cited Findings

- **Experience Memory Graph，2607.13884v2，2026-08-10。** §4.1.1–4.1.2、Appendix A Algorithm 1：收集代理实际探索轨迹，配对 ETO 提供的成功专家轨迹；节点为规范化动作 `(type, object, receptacle)`，边为相邻动作间的规范化观测。相同动作复用节点；连续无效动作从上一个有效动作节点并行连出。扫描构图本身不依赖 LLM 提炼能力。§4.2 与 Appendix B Algorithms 2–3 对图匹配结果提取 common subgraph 和 edit path，然后用 LLM 把结构结果写成记忆指导。模型运行于 ALFWorld / ScienceWorld，不是任意代码动作空间。[v2 全文](https://arxiv.org/html/2607.13884v2)
- **EMG 的两种图必须区分。** 上述 action decision graph 的节点是动作；最终 experience memory graph 的节点是训练任务，边按任务 query 相似性选择，再保存跨任务 common-subgraph insights。它研究一种记忆生成算法，而不是为任意原生 agent 提供外部四维评分。专家成功轨迹不可忽略；测试期使用离线构建的固定记忆。[§4](https://arxiv.org/html/2607.13884v2#S4)
- **Trajectory Graph Copilot，2607.27443v1，2026-07-29。** §3.1 用 NLTK 规范化动作，去重形成动作节点，按实际动作序列建立连接，观测为边属性；§3.2 的邻接矩阵对同一动作对只记连接存在，多个观测用 BERT 表征平均。加入 trajectory 节点后，用 GNN 判断错误。Appendix C.3：ALFWorld / TextWorld 给出环境合法动作列表，ScienceWorld 给动作模板；C.2 的错误标签由 LLM、规则脚本和人工校验产生。因此“直接构图”已有，但并非全套评分无 LLM／无人工。[正文及附录](https://arxiv.org/html/2607.27443v1)
- **MC-EvoBench，2610.13829v1，2026-10-09。** §3.2 与 Appendix B.2–B.3：节点是 task / item / tool / location / condition 等声明对象；边是 requires / produces / consumes / enables / abstracts_to；编译有序 stage chain，图不规定实际动作序列。Appendix C.4 的 WGP 按通过阶段给预声明 requires / produces / consumes 边信用，非每次玩家转移产生边。实际 simulator 动作与观察支持谓词验收。[全文](https://arxiv.org/html/2610.13829v1)
- **MC 官方代码交叉验证。** `TaskStateGraph.from_catalog` 遍历 `catalog.edges` 构建关系索引；`compiled_chain_metric_metadata` 固定计划图边分母；`_graph_totals_from_passed_stages` 只汇总 passed stage 的 graph_paths。runner 中 graph_paths 来自 compiled stage，并非由动作日志新增图边。[graph.py](https://github.com/xzw-ustc/mc-bench-open-source/blob/main/src/mcbench/graph.py)、[metrics.py](https://github.com/xzw-ustc/mc-bench-open-source/blob/main/src/mcbench/metrics.py)、[runner.py](https://github.com/xzw-ustc/mc-bench-open-source/blob/main/src/mcbench/runner.py)
- **EvoAgentBench，2607.05202v1，2026-07-06。** §3.2 / Appendix A：LLM 跨多个 execution traces 抽取带 trigger / procedure / evidence / boundary 的 Ability cards，嵌入筛选、三 LLM 仲裁与专家审核合并能力；任务是节点，共享合格能力才连边。不是环境状态迁移图。[全文](https://arxiv.org/html/2607.05202v1)
- **EMem-Bench，2609.28236v1，2026-09-23。** §4 / Appendix B–C：作者构造并模拟执行带记忆 cue 的历史，插入 PDDL distractor；被测系统通过合法 grounded 动作继续执行，ERR 自动匹配动作与冻结触发标注。EMem 内部图是 entity / in / on / held_by 的空间记忆，不是实际通勤图。[全文](https://arxiv.org/html/2609.28236v1)

### Inferences

- 用户与 EMG / Copilot 的构图对象不同：用户保留地点身份与每次移动 occurrence，适合空间重复、折返、代价分析；EMG 保留动作—观测决策模式，适合指导错误纠正。相同动作节点合并后的图不保证可逆恢复原始 trace 次序与次数。
- **不能过度断言 EMG 丢掉每次重复边。** v2 明确 node reuse；Algorithm 1 的边更新用 `(last,v)` 及 `s_(last,v)`，没有时间索引、多重边 occurrence schema 或可逆重建证明。缺少官方代码，无法确认同一端点对不同观测是否保存为平行边，或后来属性覆盖前者。可以确定的是论文没有用户那种“每次通勤单独留边并留序”的定义。
- 同一地点在天气、时间或工具条件不同的时候不必具有相同完整环境状态。用户可继续以地点为节点，条件作为访问／边事件标签；但不能称纯地点图完整保留所有状态，也不能从“雪地→山谷”移动图恢复未移动的测量、等待、失败尝试。
- 有限操作约束能稳定绑定动作和环境状态，使自动计算更可靠；此性质在现有模拟环境已存在。用户需要研究其在记忆评价中的具体新增用途，不能只用它与 SWE-bench 的对照证明领域 novelty。

### Gaps

- EMG v2 主文与 arXiv abstract 未给可确认作者代码仓库；搜索未定位可信作者实现。结果是“论文算法核实”，不是复现验证。页面带有 2027 SIGKDD 模板／占位 DOI，不能当作已录用会议信息。[arXiv 版本页](https://arxiv.org/abs/2607.13884v2)
- Copilot 附录说接受后公开代码，未定位可确认作者实现。不能声称其动作标准化及图注入完全没有实现层误差。[Appendix C.2](https://arxiv.org/html/2607.27443v1)
- MC 源码取自公开 main；GitHub API 取 commit timestamp 遇到 403 rate limit。已保存所读源码，代码快照没有独立证实发布日期；论文 v1 本身在截止日前。

## 2. 自产记忆、独立 session 和四维能力已经被覆盖到哪里？

### Takeaway

完整研究问题不是 MemoryArena 独有，也不能靠“自产而非别人给记忆”区分所有近邻。AgentCL 同时有自主记忆、离散交互环境、稳定与泛化评测；PAST-Bench 明确保留原生持久机制并清空 session。未在本组审计论文中发现用户设定的地点—通勤 occurrence 图直接用于同一连续任务流的全部四维外部自动测量，但这是一项有限检索结果，不能升级为首次或充分 novelty 保证。

### Cited Findings

| 论文 | 实際历史与记忆 | 边界／任务序列 | 四维最近覆盖 | 是否实际 trace 直接构图作外部记忆评分 |
|---|---|---|---|---|
| [MemoryArena v2](https://arxiv.org/html/2602.16313v2) | 标准记忆循环从自身任务动作和观察 update；长上下文会自动附加 | 独立子任务 session，组内历史依赖；统一 Retrieve / Update 接口 | 累积历史需求和深度；没有本方案四个独立行为分数 | 没有；主要 PS / sPS / SR |
| [MC-EvoBench v1](https://arxiv.org/html/2610.13829v1) | source 交互形成 declared artifact，可文本、技能或参数 | 重置物理世界／库存；fresh target agent；read-write source、read-only target | 主实验前向迁移；框架可扩展 retention / composition，不代表全文都实际实验了 | WGP 是阶段依赖图进度，非动作 occurrence 图 |
| [EvoAgentBench v1](https://arxiv.org/html/2607.05202v1) | automatic methods 在 train tasks 上自己 rollout、形成 evolution state；Anchor 为 curator routing 诊断参考 | train/evolve/test 分开，实例不重叠 | 获取与迁移、负迁移；非延迟保持／失败纠正四维协议 | graph用于task relation和split，非执行状态变化 |
| [EMem-Bench v1](https://arxiv.org/html/2609.28236v1) | 给定作者生成历史，系统自行 write/query；有显式 human correction 来源 | episode-local 空记忆；历史 ingestion→target execution | 故障经验／generalization／动态更新；不是完整自产历史流 | grounded动作 ERR；图是内部 memory |
| [PAST-Bench v1](https://arxiv.org/html/2608.04003v1) | native memory/skill/history/artifact，从 learn/update episodes形成；部分 information gathering 参考预先seed | fresh session，匹配 persistence on/off；cold/learn/eval/control角色 | retention horizon、update、stale／wrong／distractor controls；不同四分类 | trace expectations＋关键词／读写计数／grader，非地点通勤图 |
| [AgentCL v3](https://arxiv.org/html/2606.02461v3) | 明确没有GT guidance，自主 synthesize memory；多种记忆方法 | first-pass读写、second-pass只读；heldout frozen memory；同框架接口，未证明native工作区边界 | PG / SG / GG，负SG或GG揭示稳定性／干扰；未定义单独失败纠正分数 | SR / PR / accuracy，未生成执行路径图评分 |
| [EMG v2](https://arxiv.org/html/2607.13884v2) | 自跑探索＋专家成功轨迹共同离线生成记忆 | train/test明确分开，test固定memory | 错误纠正与seen/unseen迁移，不是四维评测器 | 直接trace图存在，但用于生成记忆 |
| [Copilot v1](https://arxiv.org/html/2607.27443v1) | 历史轨迹训练错误检测器，在线给外部反馈 | 单任务全历史、每步可重提动作；没有native跨session记忆处理 | step错误与恢复，非持久记忆四维 | 直接trace图→GNN分类；不是任意agent memory评价 |

- **AgentCL 环境并非相关工作引用。** 当前 v3 为 2026-09-26，v1 为 2026-06-01；两版均有真实 BabyAI / ScienceWorld 实验。v3 §4.1 Table 1：BabyAI dependent28+28、conventional40；ScienceWorld conventional90。主文 Table 3 给 BabyAI SR/PR，Appendix B.8 Table 13 给 ScienceWorld conventional/block SR/PR，B.13 Table 19 给36 heldout BabyAI。v1对应用词为 compositional/naive，构造细节在B.9；不要混用版本编号。[v3](https://arxiv.org/html/2606.02461v3)、[v1](https://arxiv.org/html/2606.02461v1)
- **AgentCL §3.1 的自产限定明确。** 原文短片段：“memories entirely on its own”。BabyAI 简单到组合导航、开门、拾取、解锁关系，由该论文实验实际使用；该论文没有专家正确记忆作为标准被测输入。其统一memory接口与用户原生完整agent机制仍需分开。[v3 §3.1](https://arxiv.org/html/2606.02461v3#S3.SS1)
- **PAST native边界非常接近。** Appendix E.1 在一对比较内保持prompt/tools/model/context政策相同，只变保留状态可访问性；§3.2用task-family expectation与trace核查写入→检索→应用，但作者没有把机制证据等同因果证明。[正文与Appendix E](https://arxiv.org/html/2608.04003v1)
- **The Compliance Trap 的可控触发已存在，但记忆不同。** §3.3 / Appendix D 的 MemTrapBench 由固定HTML/JS骨架、可执行UI、正确路径和trap操作构造，任务按Entry/Uptake/Grounding/Override组织；记忆是手写或Claude起草后人工审核的helpful/conflicting/control passages。它研究外部给定记忆的消费，不是agent自主生成记忆。[全文](https://arxiv.org/html/2607.10608v1)

### Inferences

- “完整native agent”与“自产经历”是两个限制：AgentCL/MemoryArena的历史可以自产，但记忆Update/Retrieve是统一接口；PAST确实更接近native整体系统。无法用自产经历把前两者排除。
- 连续每任务可学可复用，与source/eval分阶段有实质protocol差别，但仅改变日程不自动形成新科学发现。还要说明日程为什么改变四维结论、测量覆盖或可靠性。
- 用户的external movement graph与EMG internal correction memory用途不同；因此EMG不会直接否定全部benchmark方向，但会否定“首次从受约束trace算法构图”的狭窄主张。
- 预设任务条件后自动从动作判分本身已由ERR和PAST expectation contracts覆盖；记忆影响路径的诊断已由Compliance Trap部分覆盖，只是它用外部构造记忆。

### Gaps

- 本审计没有独立复现AgentCL的session清理和native持久工作区适配器，不可称其与用户原生完整agent协议完全相同。
- 本审计未发现一篇已完成“连续自主探索＋native独立session＋直接地点通勤多重图＋全部四维行为测量”的等同方案；其他研究者在查导航与符号规划，最终结论须合并，不可以把此局部未找到当作全球未存在。

## 3. 对 novelty 的可复核判断与阅读覆盖

### Takeaway

用户指出的是正确的环境设计优势：用明确动作效果定义可审计trace，比开放代码工作区更容易直接构图。但它在离散模拟环境与trace图方法中已有先例，单独作为核心novelty不够。基于本组证据，只能支持“评测协议和表示用途有组合差异”，不能确认达到论文贡献阈值，也不能断言整个研究没有意义。

### Cited Findings

- 直接trace算法构图、保持动作反馈关系：EMG和Copilot已有；任务约束产生可验证行为与图上阶段评价：MC已有；自产记忆在相同/相关符号任务中跨任务收益与稳定性：AgentCL已有；native fresh-session持久状态对照：PAST已有。[EMG](https://arxiv.org/html/2607.13884v2)、[Copilot](https://arxiv.org/html/2607.27443v1)、[MC](https://arxiv.org/html/2610.13829v1)、[AgentCL](https://arxiv.org/html/2606.02461v3)、[PAST](https://arxiv.org/html/2608.04003v1)

阅读状态如实记录（原文下载在 `memory_graph_sources`，数学已转latex以减少HTML重复；下载不等于已完整阅读）：

| 论文 | 本轮实际核查覆盖 | 代码／数据核查 |
|---|---|---|
| EMG v2 | 正文问题、收集、构图、匹配、记忆生成、检索、实验设置与主要结果；附录A–E与Algorithms1–3逐段核查。不是只看摘要 | 未找到可确认作者仓库，不能声称代码级实现确认 |
| MC v1 | §3全方法、实验设置；Appendix A–E、G中环境、图编译、评分、artifact边界和适配器逐段核查；catalog结果大表不用于结构结论 | 阅读 graph.py / chains.py / metrics.py / runner.py / schema.py；只做静态核查 |
| EvoAgentBench v1 | §3构造、§4协议和diagnosis；Appendix A–C、E的抽取、merge、split、信息权限与scaffold核查 | 论文没有定位可确认的作者图生成实现；未声称复现 |
| EMem-Bench v1 | §4–5、Appendix B.1–B.3、C.2逐段核查；其余全文已获取，非所有结果表都细读 | 本轮未读作者完整实现；ERR结论限论文明确说明 |
| MemoryArena v2 | §3.1–3.2、§4.2、Appendix A.2 / B.1方法完整核查；先前长文已读，本轮重新检查动作限制与memory接口 | 本轮未新增逐文件代码核查 |
| AgentCL v3 / v1 | v3 §3–5、B.8/B.13/B.14，v1对应章节和表核查；确认真实符号环境与自产记忆 | 本轮未代码验证session边界 |
| PAST v1 | §3完整方法、Appendix B评分与E.1session/native边界逐段核查；其余全文已获取 | 本轮未完整代码核查 |
| Compliance Trap v1 | §3、Appendix D环境构造、E.2控制设计核查 | 未以其合成memory结果替代用户自产memory |
| CL-Bench v1 | 全文获取；本组未深核其六域，不用它作精确图重叠论据 | 交由其他组补充 |
| Copilot v1 | §2–3、§5、Appendix C.1–C.6逐段核查，特别是available actions与graph schema | 未找到公开作者实现，论文称接受后公开 |

### Inferences

- 可给用户的明确答复：**这种构图机制有很近先例；它不是凭空无效，也不是已经独有。** 构图方法若仍只是地点边投影加传统图统计，单独方法创新薄弱；完整benchmark能否成立取决于任务体系、四维测量定义与实证结果，而不是必须另发明记忆算法。
- 候选优势可以直说为environment-grounded、可确定计算、无内部memory格式限制、保留移动occurrence；这些都是可测试的设计优点，不是声称首次的依据。
- 不应再向用户提出与研究目标脱节的“新增诊断就必有novelty”。如果目标只是自产记忆帮助相似任务，而新增图无可区分测量价值，那么本组证据不足以建议为守住图设定继续开发大游戏。
- 地点-通勤表示与动作-观测表示可以比较信息损失与测量可靠性；这仍是待检验方向，不能把换节点定义包装为新理论。

### Gaps

- 本组没有测试用户原四维指标或生成新分数，不能确认其构念效度或统计可靠性。
- 没有同等任务上的实验，不能证明图评分优于总成本、局部事件评分或成功率。
- 无法保证投稿novelty或接受；当前能确定的是关键单项先例和具体协议差别。
