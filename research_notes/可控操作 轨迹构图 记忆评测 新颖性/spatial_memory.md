# 可控操作、地图图与自产记忆：空间导航先例审计

核查日：2026-10-15。范围限定公开日期不晚于此日。全文材料及官方代码只读副本位于 `spatial_sources/`；没有运行下载的模型/环境代码，没有复现实验。检索和阅读区分：R2R 主文通读；IVLN 主文及附录 A–C 通读；GOAT 主文及附录 A–D 通读；nDTW 主文及附录 A–C 通读；CLS 主文通读；MemTransfer 主文通读（没有独立附录）；FindingDory 主文通读、附录 B.1–B.3、E.2 精读，其他长提示/训练附录未全部读；RoboMemArena 主文通读、附录 10/11 定向阅读。这里“通读”指全文文字、公式和图表说明，未逐幅检查图片像素，未逐项核对全部参考文献。

## 一、固定合法动作产生确定地点转移，再生成可控图轨迹，是否已有直接先例？

### Takeaway

有，而且直接先例早于 LLM agent：Matterport3D/R2R 的模拟器就是加权地点导航图，动作只能选择当前可达的地点，执行确定地改变位置。实际动作产生有序节点序列，可以无语义抽取地转换为用户所说的带序号通勤多重图；换一个存储数据结构不是新的构图原理。

### Cited Findings

- **R2R（CVPR 2018），最直接的结构先例。** §3.2.1 用全景采样地点定义位置节点，方向/相机俯仰另存。§3.2.2 明确动作确定，合法目的地点由当前导航图邻居及视野限制决定。环境图的边来自 3D 障碍检测、距离限制与人工核验，边权为位置间距离；§4.1 把实际执行定义为状态—动作序列。不是对任意自由文本工作流事后猜图。— [全文 §3.2–4.1](https://arxiv.org/html/1711.07280)
- **官方代码确证“动作约束→确定转移”。** `src/lib/MatterSim.cpp` L501–537 的 `makeAction`：越界动作 index 抛错；L519 把位置直接设成 `navigableLocations[index]`；L523 递增 step；随后更新朝向及可达集合。— [固定版本源代码](https://github.com/peteanderson80/Matterport3DSimulator/blob/589d091b111333f9e9f9d6cfd021b2eb68435925/src/lib/MatterSim.cpp#L501)
- **官方环境图构建确证。** `tasks/R2R/utils.py` L19–44：从 connectivity JSON 的稳定 `image_id` 与 `unobstructed` 标注构造 NetworkX 加权无向图。— [load_nav_graphs](https://github.com/peteanderson80/Matterport3DSimulator/blob/589d091b111333f9e9f9d6cfd021b2eb68435925/tasks/R2R/utils.py#L19)
- **官方实际 trace 生成确证。** `tasks/R2R/agent.py` L219–223 记录出生位置；L269 执行动作后，L272–275 把新的 viewpoint、heading、elevation 追加到列表。访问同一个地点多次不会被去重合并。— [rollout](https://github.com/peteanderson80/Matterport3DSimulator/blob/589d091b111333f9e9f9d6cfd021b2eb68435925/tasks/R2R/agent.py#L219)
- **实际路径的合法性和成本自动核验。** `tasks/R2R/eval.py` L47–72 逐个相邻位置检查地图是否存在边，非法跨越报错，累加每次实际转移的距离。原论文 §4.4 主要看终点成功，不评价全轨迹；官方后续代码已有长度与 SPL，必须区分版本。— [eval.py](https://github.com/peteanderson80/Matterport3DSimulator/blob/589d091b111333f9e9f9d6cfd021b2eb68435925/tasks/R2R/eval.py#L47); [原文 §4.4](https://arxiv.org/html/1711.07280)
- **图上全路径自动比较也已有。** CLS（ACL 2019）§2.1/§3 定义环境图节点为位置、边为合法移动、实际路径为访问节点序列；§3.3 用图最短距离构成覆盖与长度分数。nDTW（2019）§2/附录 B 用图最短距离作节点对代价，通过有序动态规划比较整条路线，复杂度 O(|R||Q|)。二者比较实际与参考路线，非仅终点。— [CLS 全文](https://arxiv.org/html/1905.12255); [nDTW 全文](https://arxiv.org/html/1907.05446)

### Inferences

- 用户的 `雪地→山谷→雪地→森林` 与 R2R 的 `viewpoint_a→viewpoint_b→viewpoint_a→viewpoint_c` 在移动建模原理上相同：环境约束合法操作，得到确定地点访问记录。语义地区 ID 比视觉 viewpoint ID 更粗，但不是根本不同的生成方式。
- 由节点序列 (v_0,...,v_T) 生成 (e_k=(v_{k-1},v_k,k))，就是图上的 walk 的可逆表示。地点合并、每次移动保留为独立有向多重边、以 k 保留顺序，均可直接从既有导航日志得到。不能用“论文没写 MultiDiGraph”推断它不能得到相同表示。
- 此方式相对 SWE-bench 的优势真实：固定动作 API 和模拟器位置提供可靠构图基础。它是把研究转入合适可控环境的理由，但不足以独立支撑首次提出的 novelty。
- 地点图是完整环境状态的投影：朝向、时间、工具、天气可以不同而位置相同。不要说“只有两个状态”，应说“地点投影只有两个节点”。完整图不必展开所有组合，但非移动动作和条件必须另外记录。

### Gaps

- R2R 单任务协议不测自产持久记忆跨独立 session 的四维能力。因此它直接覆盖构图原理，不覆盖用户完整研究协议。
- 没有检索到证明“带序号多重边存储本身”优于完整有序节点/事件日志的新测量能力；这种优势需要具体算法或实验，不能由存储形式直接推断。

## 二、最接近的空间记忆 benchmark 怎样产生历史、轨迹和评分？

### Takeaway

IVLN/GOAT 已将环境动作约束、实际探索、自身记忆累积、后续导航收益及自动路径评分结合；这是不能漏掉的最重要一组相关工作。FindingDory/MemTransfer 也具备可靠动作与轨迹记录，但历史是 oracle/专家提供，协议与用户自主探索的连续独立 session 明显不同。

### Cited Findings

#### IVLN / IR2R / IR2R-CE（CVPR 2023，最强直接近邻）

- §1/§3：离散版直接在导航图边上移动，最多 100 个指令任务构成同场景 tour，agent 在执行任务时累积部分环境信息，不要求全图预探索。每任务提供语言指令与评测参考路径。连续版在 3D navmesh 上执行固定移动/转向/STOP。— [全文 §1–3](https://arxiv.org/html/2210.03087)
- §3 的 t-nDTW：把各任务实际节点/位置序列与参考序列组成 tour，DTW 不允许跨任务配对，oracle 移动排除评分，按 tour 所含任务数加权。作者专门指出逐任务简单平均会让第一次全图探索成本被长序列稀释。公式为 `exp(-DTW/(|R|*d_th))`；离散版用图距离。— [全文 §3，Metrics for Iterative Evaluation](https://arxiv.org/html/2210.03087)
- **不能描述为纯自产经验-only。** 主文 §3：每任务结束后 oracle 首先带失败 agent 去正确终点（0.5m 判断），再去下一任务起点，agent 被动观察沿途。§4.1 TourHAMT 的历史明确包含 oracle 阶段状态—动作。附录 B 的正式隐藏 test 为避免泄露终点，去掉 oracle-to-goal，只带去下一任务起点，并重新生成 train/val 作一致对照；仍有外部控制移动。— [全文 §3、§4.1、附录 B](https://arxiv.org/html/2210.03087)
- `ivlnce_baselines/common/environments.py` L79–85 每步记录 position/phase/episode_id；L234–287 实现 oracle 移动；L313–345 区分 agent 与 oracle 阶段，配置可关闭 goal oracle。— [固定版本 environments.py](https://github.com/jacobkrantz/IVLN-CE/blob/14417fc0930fc273183667c09e3e3564adc823a0/ivlnce_baselines/common/environments.py#L79)
- `habitat_extensions/tour_ndtw.py` L40–66 排除 oracle 并限制 episode 边界；L94–130 直接读运行日志执行 DTW。注意连续版代码用位置距离默认值（Euclidean），与主文所称 geodesic 距离有实现差异，不宜声称所有版本代码严格兑现图 geodesic。— [tour_ndtw.py](https://github.com/jacobkrantz/IVLN-CE/blob/14417fc0930fc273183667c09e3e3564adc823a0/habitat_extensions/tour_ndtw.py#L94)
- §4.2 的 MAP-CMA 由实际 RGBD 与 pose 构建 occupancy/semantic 地图；比较每任务重置、全 tour 累积、已知地图，后者 oracle 不允许 leaderboard；§5.2 观察累积地图收益。它是内部记忆图/网格，评分输入另为实际路径序列。— [全文 §4.2–5.2](https://arxiv.org/html/2210.03087)

#### GOAT-Bench（CVPR 2024，自主连续探索的强先例）

- §3：一条 episode 有 5–10 个目标，任务成功或预算耗尽后直接发下个目标，不重置场景。固定动作包括移动 0.25m、转向/抬头低头 30° 和 stop，每子任务 500 动作预算。§5 的隐状态或显式地图来自实际执行观察，非提供专家历史。— [全文 §3、§5](https://arxiv.org/html/2404.06609)
- §6/§7.2–7.3：SR 与 SPL；每子任务参考最短路从上一子任务实际终止位置计算。清空显式地图/隐状态的对照，分析保留记忆对后续路线效率的作用。没有统一四维延迟保持/失败纠正/干扰评分。— [全文 §6–7](https://arxiv.org/html/2404.06609)
- `goat_bench/measurements/nav.py` L344–416 的 GoatSPL 从模拟器读取实际位置，逐步累加行走距离，子任务 stop 时计分，并更新下一子任务起始参考距离。`goat_bench/trainers/ppo_trainer_no_2d.py` L210–224 用子任务 stop mask 清空 recurrent states 作 ablation。— [GoatSPL](https://github.com/Ram81/goat-bench/blob/74c41d19d4a4c3608d1575b512087b5a529aee0e/goat_bench/measurements/nav.py#L344); [memory ablation](https://github.com/Ram81/goat-bench/blob/74c41d19d4a4c3608d1575b512087b5a529aee0e/goat_bench/trainers/ppo_trainer_no_2d.py#L210)

#### MemTransfer（2026-09-26，固定操作与可控路线变化高度接近）

- §III-A：Isaac Sim 仓库划分 1m 格子和四方向，固定前后左右移动与转向，障碍移动原地反馈且消耗一步；不提供地图或物品位置表。§III-B：100 个任务，600 参考轨迹来自真实地图规划器及回放验证，历史来自成功专家示范；新起点、阻断旧通路、相关/无关/混淆历史是三个受控操纵。— [全文 §III-A/B](https://arxiv.org/html/2609.32313v1)
- §III-C/§IV-B：历史记忆测试期间固定，当前工作窗口更新；SR、SPL、阻断点尝试率、尝试后恢复率自动从执行算。其“retention”是封路成功率相对于原路线成功率的比例，并非经历其他任务后的记忆保持。§V 明确未来才考虑在线更新/遗忘。— [全文 §III-C、§IV-B、§V](https://arxiv.org/html/2609.32313v1)

#### FindingDory（2025，动作/状态验证成熟，但不是被测 agent 自己采集历史）

- §3.1 与图1：privileged oracle 采集随机物体搬放历史，然后被测 agent 读取视频/pose/actions 执行模板任务；§3.2 有固定导航动作，PDDL predicates 对实际模拟器状态自动检查。附录 B.2 的采集策略包括 shortest-path 导航、硬编码 magic pick/place、预存放置动作回放。— [全文 §3 与附录 B.2](https://arxiv.org/html/2506.15635)
- §4.2/附录 B.3：高层目标选择与低层导航的成功和 SPL 分开评估；多目标采用满足所有目标的最短路径参考。附录 E.2 的 occupancy map 在 oracle 采集阶段由深度/pose 建立，规划器返回固定动作路线，不是统一外部自产记忆四维评价。— [全文 §4.2、附录 B.3/E.2](https://arxiv.org/html/2506.15635)
- 官方 `findingdory/policies/heuristic/oracle_agent.py` L40–59 明确 OracleAgent 与 simulator greedy follower，L79–84 使用 HeuristicPlace/PickPolicy。— [官方代码](https://github.com/findingdory-benchmark/findingdory-habitat/blob/0c8af9a434143e774cf28c4d2ccd4843b9846cfd/findingdory/policies/heuristic/oracle_agent.py#L40)

#### RoboMemArena（2026-05-11，原子操作与可验证状态，但长单任务机器人记忆）

- §3.2：VLM 拆子任务，经人工纠正后由 AnyGrasp 和预定义原子 primitives 生成成功示范，后置条件检查失败就重试，物理/速度事件抽取关键帧；§3.4 根据多个执行状态 predicates 得 TSR/CSR。§4 中 PrediMem 在线决定写入关键帧。主要是同一长操作序列内的遮挡/计数/顺序/搬运，不是跨独立 session 的持久经验流。— [全文 §3.2–4](https://arxiv.org/html/2605.10921)

### Inferences

- **真正需要比较的三种对象不同**：环境合法移动图（R2R）；模型内部构建地图/记忆（MAP-CMA/GOAT）；评测侧实际有序 walk（R2R/IVLN）。用户的轨迹图属于第三种，不应只拿第一/第二种方法比较。
- IVLN 和 GOAT 已反驳“只有用户能由实际操作得到可控轨迹、别人只看终点”的论点。IVLN 甚至针对跨任务轨迹聚合提出新评分；GOAT 的持久记忆 vs 清空对照直接观察效率收益。
- 用户仍有协议差异：LLM 完整原生持久系统、真正无历史上下文的新 session、四维实验关系、自由探索失败也产生后续经验、无 oracle 强制补课。但这些差异不是每项都新，也不能仅合并四个名称就认定贡献充分。
- MemTransfer 同样能由受限动作生成图上路线，且适应/干扰操纵很接近；其固定专家历史不是自主采集和管理，可正面作为协议对照，不能排除为“不是图”。

### Gaps

- MemTransfer 正文未提供可直接核查的公开完整代码链接；动作与指标以论文协议为准，未复现实验。
- 没有发现上述全文已经实现用户完整的“独立 LLM session + 原生自产记忆 + 四维 + 地点通勤图外部评分”组合。但本子任务范围不是全领域穷尽，不能宣称首次组合。
- MemoryMaze、MultiON、SPTM 仅检索定位未通读：分别涉及记忆迷宫、序列多目标地图记忆、从探索影像建立内部拓扑图，不用于否定完整方案。— [MemoryMaze](https://openreview.net/forum?id=yHLvIlE9RGN); [MultiON](https://arxiv.org/abs/2012.03912); [SPTM](https://arxiv.org/abs/1803.00653)

## 三、哪些主张已经被覆盖，哪些只能作为待验证贡献？

### Takeaway

仅“固定操作把执行压到已知地图上，因此可自动得到图轨迹”已有极直接先例，不能作为核心原创点。完整协议可能有未被同一先例完全覆盖的价值，但必须提出并验证四维评价的新增能力，不能把 session 文件边界或格式差异当充分 novelty。

### Cited Findings

- 导航图约束合法动作、执行确定转移：R2R 已有。— [§3.2.2](https://arxiv.org/html/1711.07280)
- 实际有序路线、全路径图距离评分：CLS/nDTW 已有。— [CLS §3](https://arxiv.org/html/1905.12255); [nDTW §2](https://arxiv.org/html/1907.05446)
- 自主执行获取部分空间经验、后续任务复用、清空地图/隐状态对照：IVLN/GOAT 已有。— [IVLN §4–5](https://arxiv.org/html/2210.03087); [GOAT §7.2–7.3](https://arxiv.org/html/2404.06609)
- 新起点泛化、旧路线失效、混合历史影响、自动恢复指标：MemTransfer 已有，但源历史为专家且测试记忆固定。— [§III-B/IV-B/V](https://arxiv.org/html/2609.32313v1)

### Inferences

- 给协调者的证据结论：**用户提出的构图可控性是有用的实验属性，不是目前可主张的新构图方法。最需要解释和引用的直接先例是 R2R 与 IVLN，而不是只比较 MemoryArena。**
- 不建议硬凑“外部图 vs 内部图”“多重边 vs 数组”“有四维 vs 一个综合分数”作为突破。这些最多是实现/协议差异；若评分从有序路径直接可算，换图容器没有额外信息。
- 若用户坚持把“操作生成图”作为唯一 novelty，现有证据不支持继续围绕该主张写贡献。若愿意把图作为已知技术基础，完整 benchmark 可否成立应由其他研究者核查原生自产记忆协议和四维识别的最邻近工作，并由实际对照验证新增解释力。
- nDTW/CLS 评价参考路线一致性，不自动测记忆，也不保证适合自由制图探索；完美知识最短路惩罚首次合理探索，不能直接读作记忆失败。用户不能因先例存在就照搬单一固定最优路径评分。
- 保留自主探索与实际证据历史，在已获得/未获得经验情况下对分支行为作不同解释，是合理的测量需求；本笔记未证明其首次，也未证明足够论文 novelty。必须避免替用户将有效性要求包装成新研究问题。

### Gaps

- 未找到完全同构完整协议 ≠ 已确认 novelty；构图已有 ≠ 完整研究无意义。这两种结论都超出现有证据。
- 没有实现用户新指标，无法证明图分析优于 SR/SPL/nDTW/局部事件评分。不会给出虚假的“肯定够/肯定整个方向不够”判决。
