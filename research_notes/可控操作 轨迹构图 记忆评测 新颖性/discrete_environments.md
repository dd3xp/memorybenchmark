# 固定操作、合法转移与可直接构图的交互环境：新颖性核查

## 1. “环境约束操作 → 精确状态/位置变化 → 直接构图”有没有直接先例？

### Takeaway

有，而且并不限于抽象的 MDP 定义。TextWorld 直接描述如何用规则生成状态转移图，其地图也直接由房间图构造；ALFWorld、ScienceWorld、MiniGrid 的正式环境与代码都把操作的条件、状态修改和位置变化写在模拟器内。用户相对于 SWE-bench 的可观测性优势成立，但不能作为相对于交互游戏环境的独有构图原理。

### Cited Findings

- **TextWorld（2018），最直接的基础机制先例。** §3.1 的状态是逻辑事实，动作是满足前置条件的规则实例；规则应用产生 `(s,a,s')`，forward chaining 构造 proof-tree，合并重复状态得到底层转移系统。§3.2.1 按 random walk 生成房间连接地图。§3.1.1 跟踪实际状态，动态调整完成任务所需动作，并据路径增减提供中间奖励。它不是从自然语言 trace 事后用 LLM 猜一个图。— [全文 §3.1–3.2](https://arxiv.org/html/1806.11532v2)
- **TextWorld 官方代码直接证实。** `textworld/generator/world.py` 的 `World.from_map`（本次下载行 168–177）接受 `networkx.Graph`，`graph2state` 转为逻辑事实；`textworld/logic/__init__.py` 的 `State.is_applicable`（1692–1696）、`State.apply`（1717–1736）检查前置条件，并增加／删除动作效果事实。因此真实地点和行动语义不是事后抽取的。— [World 源码](https://github.com/microsoft/TextWorld/blob/main/textworld/generator/world.py#L168); [State 源码](https://github.com/microsoft/TextWorld/blob/main/textworld/logic/__init__.py#L1692)
- **ALFWorld（ICLR 2021）。** §2 使用共同的 PDDL 潜在结构对齐文字和具身环境。附录 C 明确谓词状态、动作生产规则与状态更新；附录 G 的 `goto` 返回 `loc_id`，失败或无变化操作返回无变化反馈。注意文字版高层 `goto` 与具身版多步控制不同，后者不宜一概称确定性。— [全文 §2、附录 C/G/I](https://arxiv.org/html/2010.03768v2); [官方环境入口](https://github.com/alfworld/alfworld/blob/master/alfworld/agents/environment/alfred_tw_env.py)
- **ScienceWorld（2022）。** §3、附录 A.2/A.3：10 个地点及固定连接，25 类参数化操作，由解析器唯一解析并交给模拟器。附录 B.4 的 required/optional goals 自动检查状态，但允许多种解法。地点变化可从环境确定，不必语义判断。— [全文 §3、附录 A/B](https://arxiv.org/html/2203.07540v2)
- **ScienceWorld 移动代码。** `ActionMoveToLocation.scala` 的 `ActionMoveThroughDoor.runAction`（18–69）先检查合法性，再把 agent 放入目的地点；`isValidAction`（86–151）检查是否存在相连 portal、是否通行，失败不执行移动。这与“雪地 → 山谷”的位置转移机制直接同类。— [官方源码](https://github.com/allenai/ScienceWorld/blob/main/simulator/src/main/scala/scienceworld/actions/ActionMoveToLocation.scala)
- **BabyAI/MiniGrid（ICLR 2019）。** §3.1、附录 B：格点位置、方向、对象与门的离散状态；七种操作；任务 verifier 检查行动序列。MiniGrid `step`（本次行 525–595）直接修改位置／方向／物品，前方不可通过时不移动。它主要研究 grounded instruction learning，不是原生持久记忆四维 benchmark。— [论文 §3、附录 B/C](https://arxiv.org/html/1810.08272v3); [官方 step 源码](https://github.com/Farama-Foundation/Minigrid/blob/master/minigrid/minigrid_env.py#L525)
- **MiniHack（NeurIPS 2021）。** §3.1 用 des-file/DSL 编译关卡，§3.3 按研究问题限制动作；附录 B.4 用事件、顺序或组合事件定义奖励／终止。附录 C.1 的 Memento 明确在走廊分岔处用前面线索选路，考察的是同 episode 记忆。它部分机制有随机性，不能把固定操作误写成确定环境。— [全文 §3、附录 B.4/C.1](https://arxiv.org/html/2109.13202v2); [官方动作文档](https://minihack.readthedocs.io/en/latest/getting-started/action_spaces.html)
- **Crafter（2021）。** §3、附录 F：17 种固定操作和明确操作要求；格点地图、位置和 semantic grid 可供评测侧读取。不存在材料时相应制作操作无效；夜晚和自动生物过程可以变化。主要评测 22 项成就，不是每任务轨迹多重图的四维记忆评分。— [全文 §3、附录 F](https://arxiv.org/html/2109.06780v2)

### Inferences

- 用户所说的约束应准确理解为**模拟器操作接口＋合法性条件＋效果＋目标判定**，不是要求 agent 遵守一条提示中的固定工作流。前者仍然允许开放探索。它与以上环境的建模逻辑同类。
- “稳定地点作节点，实际移动作边”可写为环境状态的地理投影。状态 `s_t` 经动作成为 `s_{t+1}`，读取环境地点 ID `p(s_t)`、`p(s_{t+1})` 即能加入对应通勤边。该确定转换不等于 agent 策略确定，也不等于世界完全没有随机性。
- **环境转移图**包含所有允许的状态转移；**实际轨迹图**只包含这次真实发生的动作／通勤。TextWorld 的转移系统构造是直接先例，但不能因此宣称它正式提出了用户的“每次通勤一个独立边、含顺序的外部记忆评分图”。
- 一个地点不等于完整 simulator state。同在山谷，时间、天气、持有工具等仍可不同；地理投影可精确记录位置过程，却不是对完整工具 trace 的无损压缩。可保持地点节点，并给访问／动作关联事实日志，不必强制扩张所有状态节点。

### Gaps

- 这些环境的代码可以支持记录位置变更并构图，但**可支持**不是**论文已经以该图评价四种跨 session 自产记忆能力**。目前没有在上述环境论文中找到后一完整协议的明示定义。
- 用户的新环境还没有完整操作语法、前置条件／效果、四维自动评分公式。不能把“图可直接生成”跳成“全部记忆能力可识别”的定理。

## 2. 已有工作怎样把真实执行与任务约束结合，自动评价过程？

### Takeaway

自动评价状态变化、任务子目标和探索行为已有直接工作。最近的基础先例是 AgentBoard；其评分依赖预标必要观察或目标谓词，而不是把实际所有通勤作为多重边后做记忆效果评价。应据这个精确差别比较，不能说它没有过程评价。

### Cited Findings

- **AgentBoard（NeurIPS 2024 Datasets and Benchmarks）。** §2.2 每步计算状态匹配或人工标注子目标完成，§4.3 分析动作合法性、随步数进展、六类子技能；附录 E 统计 BabyAI 房间、ALFWorld 容器、Jericho 地点的探索数量。附录 L.1 部分限制工具／方法以便标注，仍允许不同绕行轨迹；L.2–L.6 用观察匹配或 PDDL 谓词评分。这里的 memory 子技能主要指上下文内长程信息使用。— [全文 §2.2/4.3、附录 E/F/L](https://arxiv.org/html/2401.13178v2)
- **AgentBoard 代码。** `agentboard/environment/alfworld/alfworld_env.py` 的 `step` 更新环境反馈，`_check_temperature_string` 对观察做正则匹配并置完成标志，`_get_reward` 汇总子目标。`_process_ob`（95–98）反而删掉 `You arrive at loc ...` 的前缀，说明其主要评分没有使用该地点 ID 来生成通勤评测图。— [官方代码](https://github.com/hkust-nlp/AgentBoard/blob/main/agentboard/environment/alfworld/alfworld_env.py#L61)
- **AgentBoard BabyAI wrapper。** `history` 保存行动和奖励；`update_reward`（101–128）匹配预标观察，支持不同标注路径；`update`（132 起）保存动作／观察。没有在这些已审计方法中发现把重复通勤建为 multiedge 并计算四维记忆作用。— [官方代码](https://github.com/hkust-nlp/AgentBoard/blob/main/agentboard/environment/babyai_env.py#L101)
- **Memory Gym（JMLR 2025）。** §3.2.2 Mystery Path 是隐形路径探索；偏离回起点，必须记住走过路径和错误位置，endless 版本对重复同点失误设置终止。§5.2 用多个训练 seed 和未见地图 seed 评价 GRU/Transformer-XL。它确有程序化路径、错误复发、记忆收益的先例，但研究的是 episode 内的神经记忆，不是 task session 间自主写出的原生持久库。— [全文 §3.2.2/5.2](https://arxiv.org/html/2309.17207v4); [正式发表页](https://www.jmlr.org/papers/v26/24-0043.html)
- TextWorld Treasure Hunter §5.2 的设计已经明确要求高效导航、避免无关房间重访并记住目标；但 §5.2.1 的 one-life 测试有意让 agent 只见每个地图一次，防止记住该地图。其目的与连续跨 session 经验保留不同。— [原文 §5.2–5.2.1](https://arxiv.org/html/1806.11532v2)

### Inferences

- 对用户的主要优势，应写“环境结构让外部行为表示可复现”，而不是“首次能自动分析 trace”。AgentBoard 已经利用受控环境自动检查执行过程。
- 用户的通勤多重图可以特别保留绕行、反复探索和顺序；AgentBoard 的完成标志通常单调累计，无法仅从一个完成比例恢复这些重复移动。二者测量对象不同，但新测量对象仍需证明与四维记忆的对应有效性。
- 移动有代价和完成更快更好，也早见于 MiniGrid reward、TextWorld 中间奖励。若最后只计算路径长／步数，图化没有显示比已有导航成本更多的测量能力。
- 在上游岔路口因历史经验提前规避是路径层行为，可由地理图定位；判断其是否来自记忆，仍须经历记录和 retain/clear 对照。确定构图解决表示和观测问题，并不独自解决记忆归因。

### Gaps

- 尚未运行这些环境或复现论文结果；所有代码结论来自静态审计。
- AgentBoard 的六类子技能赋分不是用户四维完整协议；不能以词语 memory/self-reflection 的重叠直接宣称同一个研究问题。
- 不把单个失败尝试自动转换成“已知普遍条件规则”。实际反馈是否足够支持经验适用，需要在新任务生成／反馈设计中明确。

## 3. 完整组合哪里相同、哪里部分相似，当前能作什么新颖性判断？

### Takeaway

本分支确认：**受控动作引起可观测状态变化、由日志直接形成空间行走表示，是成熟先例；使用同一外部轨迹表示评价跨 session 原生自产记忆的四维能力，未被本分支审计的基础环境论文整体覆盖。** 因此不能把前者当独有算法创新，也不能用前者已有一票否决后者 benchmark／protocol 贡献。完整结论必须结合其他分支的近期 memory benchmarks 与导航研究。

### Cited Findings

**交叉核查补充：AgentCL 已把受控具身操作环境与自产记忆评价组合。** 主研究者转交另一分支的全文结果后，本分支再次检查 v3 §3.3/§4.1、表 3 与附录 B.13：真实实验使用 AgentBoard BabyAI 和 ScienceWorld；first pass 读取并更新经验，second pass 冻结记忆；BabyAI 同一任务族有不同环境，另有简单技能到组合技能的依赖任务流。其 PG/SG/GG 评价 plasticity、stability、generalization；不能说“受控操作环境中的自产记忆评测”尚无人做。另一方面，这不等于外部通勤多重图评分，也不能把共享记忆方法接口等同于用户对完整 agent 原生 session 的保留／清除协议。— [AgentCL 原文 §3.3/§4.1、表 3、附录 B.13](https://arxiv.org/html/2606.02461v3)

| 论文 | 固定操作＋合法转移 | 直接地理位置／状态记录 | 实际多重通勤图为核心外部评分 | 独立 session 仅原生自产持久记忆＋四维协议 | 与用户整体关系 |
|---|---|---|---|---|---|
| TextWorld | 是 | 是；还描述转移图生成 | 未明示这一评分 | 未明示 | 基础机制直接同类，整体部分相似；[§3/§5](https://arxiv.org/html/1806.11532v2) |
| ALFWorld | 是，文字与具身动作粒度不同 | 是；文字 loc_id 与谓词 | 未明示 | 未明示 | 基础机制直接同类，整体部分相似；[§2、附录 C/G](https://arxiv.org/html/2010.03768v2) |
| ScienceWorld | 是，自动过程也更新世界 | 是；固定地点及对象结构 | 未明示 | 未明示 | 固定位置转换高度相似，评分对象不同；[附录 A/B](https://arxiv.org/html/2203.07540v2) |
| BabyAI/MiniGrid | 是 | 是；坐标、朝向、网格 | 未明示 | 未明示 | 离散空间行为同类，训练与评测目标不同；[§3、附录 B](https://arxiv.org/html/1810.08272v3) |
| AgentBoard | 从模拟器继承 | 是；部分观察再加工 | 非其主要评分 | 非该协议；附录 F 为上下文管理对照 | 最近的自动过程评测先例之一；[§2.2/4.3、附录 F/L](https://arxiv.org/html/2401.13178v2) |
| Memory Gym | 是，任务程序化 | 是；隐藏路径 | 未明示 | episode 内 GRU/TrXL，不是该协议 | 路径记忆＋重复错误部分相似；[§3/§5](https://arxiv.org/html/2309.17207v4) |
| MiniHack | 是，但可含随机效果 | 是；格点／DSL | 未明示 | 未明示 | 操作约束、路径记忆和可配置奖励部分相似；[§3、附录 B/C](https://arxiv.org/html/2109.13202v2) |
| Crafter | 是，世界也自动变化 | 是；评测侧可读坐标／semantic grid | 成就评分为主 | 未明示 | 开放探索＋有限操作部分相似；[§3、附录 F](https://arxiv.org/html/2109.06780v2) |
| AgentCL | 在 BabyAI/ScienceWorld 主实验中已具备 | 从 AgentBoard 环境继承 | 表 3 用 SR/PR，非该多重图评分 | 自产记忆流已有；完整 native session 四维组合未由此确认 | 比基础环境更接近的组合先例；[§3/§4、附录 B.13](https://arxiv.org/html/2606.02461v3) |

“未明示”只表示所审计论文没有定义该项目，不能推出不存在其他工作的相同实现。

### Inferences

- **可成立的优势**：相比自由编程过程，环境能给出稳定位置、动作效果、失败原因和完整评测日志；trace→图不依赖 judge 对语义的二次猜测。这个优势有用，也更容易复现；但许多 embodied/symbolic simulators 已经提供它。
- **不能单独承担 novelty 的主张**：首次固定动作、首次通过合法转移建图、首次用图表示位置轨迹、首次自动检查探索／错误。这些都被本分支的直接证据削弱。
- **仍未定的完整贡献**：能否设计一个在连续自主探索中有效分离四种跨 session 原生记忆表现、且图上评价有独立效度的任务协议。需要说明同一地点投影保留了哪些能力差异，新增测量与已有成本、局部标记的区别；不是把内部记忆规定成图。
- 若贡献仅表述为“用模拟器生成可构图 trace”，证据不足支持强方法新颖性。若完整实验协议、判定有效性、四维能力发现都与现有工作有明确差别，可以有 benchmark 贡献；本分支不能保证发表，也没有证据要求取消整个方向。

### Gaps

**阅读和审计范围，避免把下载当通读：**

| 来源 | 实际已阅读范围 | 本分支未完成的范围 |
|---|---|---|
| TextWorld v2 | 深读 §2、§3.1–3.3、§5–7；查阅全文引言、相关工作；官方 State/World 对应实现 | 附录 B 的 50 游戏逐项清单及附录 C Inform 示例没有逐项深读；不能声称逐页无遗漏通读 |
| ALFWorld v2 | 深读 §2、主要 agent／评测部分、附录 B/C/E/G/I/J；查阅模型组件和其它附录 | 部分大型结果表与 K 全部游戏 walkthrough 未逐项核验；环境文字版核心已核实 |
| ScienceWorld v2 | 深读 §3–7、附录 A/B/C；核实移动合法性与效果代码 | 全部图中的各子任务曲线未逐点读取；附录 B 的所有任务条目未逐项代码对应 |
| AgentBoard v2 | 深读 §2.2/3/4.3、附录 B/E/F/J/K/L；检查 ALFWorld 和 BabyAI wrapper | 附录 N 的所有 prompt 与 D/I/M 细项未完整审读；不能声称全部附录逐字读完 |
| BabyAI v3 | 深读 §3、附录 B/C；检查 MiniGrid step | §4 的所有训练曲线未逐项核验 |
| Memory Gym v4 | 深读 §3、§5.2，查阅实验组织与附录索引 | 网络／loss 全部方法细节和完整结果附录未通读，非最接近 native memory 四维协议 |
| MiniHack v2 | 深读 §3、附录 B.4/C.1，查阅 C.2–C.3 | 训练算法／全部结果附录未通读 |
| Crafter v2 | 深读 §3、附录 F，查阅正文实验／全部附录索引 | 各算法成就曲线未逐图通读 |

- 支持性全文文本与本次源码副本在 `discrete_audit/`。源码是本次读取的官方默认分支快照，没有固定历史 commit；行号只用于帮助定位，发布报告应优先给函数／类名。论文版本全部早于 2026-10-15；本分支没有采用晚于截止日期的研究。
- GitHub API tree 遇到匿名速率限制，改为官方 codeload ZIP，只提取需要的源码，没有运行仓库脚本。所有来源已下载全文文本，但上表明确区分实际深读范围。
- 搜索中发现 `Experience Memory Graph: One-Shot Error Correction for Agents`（[2607.13884](https://arxiv.org/html/2607.13884v1)）；其 action-decision graph、expert 轨迹与记忆构建由另一研究分支核查，本分支不重复得出完整结论。
