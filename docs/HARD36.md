# Hard36: composition through ordinary completed tasks

Every condition has 36 scored two-stage tasks. The two stages are independent. There are 12 materials and two basic operations: catalogue (raw → catalogued) and verify (catalogued → verified). A stage publicly names its input state and desired output state. An intermediate product does not complete a combined stage.

The 24 basic experiences each have two standalone uses and two combined uses: 48 one-operation stages plus 24 two-operation stages, 72 stages and 96 necessary operations. Twelve ordinary first-round tasks expose every standalone operation. Only later tasks require combinations. There are no unscored tutorials, forced memory entries, extra data forms or source categories. A standalone verify task collects already-catalogued material; a standalone catalogue task legitimately delivers catalogued material.

`config/hard36.json` records allocation and per-map target seeds. `scripts/build_hard36.py --map <orcia|hampi|angkor> --output <path>` builds and assesses exactly one geography. Geometry, edges and station capabilities were individually compared to the preceding map and retained. All 48 processing stations in each map have strict shortest-route utility for at least one stage. The zero-model reference solutions completed all 36 tasks on each map; maxima were Orcia52, Hampi50 and Angkor44 operations, within the unchanged352-step budget. These are feasibility checks, not agent scores.

The assessment is stored beside each `*_hard36.json`. First-attempt processing metrics use required basic operations as their denominator, including an unattempted required operation. Task completion is reported separately. This design probes reuse and composition of experience; scores alone do not prove internal causal memory use.

## 2026-11-15 实跑观察

以下为 2026-11-15 21:08:57 UTC 的记录快照，均为 Hermes／gpt-5.6-luna，实际上下文272000。每张地图、每个条件各一次运行；保留组仅继承自己的学习，清除组每项恢复自己的原始基线。Easy／Normal 当时已由服务器原归档流程封存并验证内容；Hard 的任务全部完成，最终严格审计／封存当时仍在进行，以下 Hard 数字为暂定描述性统计，不代表审计已通过。

| 地图与移动方式 | 任务成功：保留／清除 | 必需操作首次处理正确：保留／清除 | 剔除每类首次遇见：保留／清除 | 总路程：保留／清除 | 模型调用：保留／清除 |
| --- | --- | --- | --- | --- | --- |
| Orcia Hard36，单步 | 36/36 ／ 36/36 | 89/96 ／ 14/96 | 71/72 ／ 13/72 | 5801 ／ 8579 | 2276 ／ 3894 |
| Capulin Easy，多步 | 16/16 ／ 16/16 | 27/32 ／ 14/32 | 21/24 ／ 10/24 | 554 ／ 703 | 462 ／ 633 |
| Nessie Normal，多步 | 24/24 ／ 24/24 | 46/48 ／ 12/48 | 36/36 ／ 9/36 | 1181 ／ 1520 | 597 ／ 1020 |

Hard 的24个组合阶段中，两项操作都首次成功的数量为保留24/24、清除1/24。处理失败尝试为35对521。首次正确率的分母是96次必需基础操作，不是36项委托或72个阶段；未尝试的必需操作仍留在分母。最终任务成功不等于首次处理成功。

保留组的 Hard 首次正确率为92.7%，Normal 为95.8%，只相差3.1个百分点；剔除每类首次遇见后为98.6%对100%。本轮保留／清除对照差距明显，但未形成明显的保留组难度梯度。当前组合可以由两条已学会的独立对应关系依次完成；增加处理次数不足以证明经验选择本身更难。不能凭 Hard 的任务数、总路程或总调用更多就认定难度梯度成立。

[汇总数据](assets/luna-paired-20261115/summary.json)保留各分母、遇见1至4、处理尝试、已报告输入／输出／reasoning和故障统计。六次物理请求故障均由原请求恢复；失败请求最终用量未知，reasoning属于输出子集。结果不用于宣称内部因果记忆使用或统计显著性。当前没有有效的同地图单步／多步对照，不能从这三张图直接判断多步优于单步。

## 后续候选：通则的适用范围与固定局部例外

状态：仅记录讨论候选，未实施、未校准，也未获得额外模型运行授权。当前 Hard36 地图、规则、任务分配、预算和所有冻结实验继续使用本文前述实现；Lunatic仍暂缓。

候选保留两个相互独立的阶段，将关注点放在经验与具体适用范围的绑定。例如，普通委托曾在A1站成功处理岩层资料，另一次普通委托在同型A2站获得不支持的反馈；后续在A2附近的任务需要记得这条局部例外，而非仅按站型套用通则。例外始终固定，公开规则必须明确说明同型站不保证完全等价，不能暗中违反当前“同型站等价”的承诺。

当前实现中，成功或失败的process都会返回本站在当前处理要求下支持的完整资料列表。候选可将反馈收窄为本次处理结果，让其他能力也通过实际任务取得。仅收窄反馈无法保证解决学完后正确率接近满分的问题；增加更多查表项也可能仍然容易。

候选核验顺序：

1. 先做少量固定例外的最小机制样例，保持现有道路与资料种类。若以后确需调整地理或站点，仍须逐图判断与核验。
2. 核对通则和例外的学习机会来自先前正常计分委托；计划遇见、实际获得反馈、保存记忆与后续行为分别记录。没有获得过相关反馈的错误不能直接算作忘记。
3. 重新计算经验的定义、分母和重复次数。加入局部例外后不能沿用“24种经验各四次”就宣称所有新规则已覆盖；先以36项为候选约束核算，缺口单独报告，不静默增加任务或更换经验口径。
4. 零模型核验只证明规则和可行性。获得新的运行授权后，再以小规模retain／clear配对实测校准，依据结果决定是否替换正式Hard；候选不预设会降低模型分数。
