# 测绘手记 · Memory Benchmark

通过完成普通测绘委托，评估 agent 自主产生、保存与复用跨任务经验的表现。Hermes 使用原生执行器；retain 与 clear 始终成对，分别拥有自己的记忆、历史、失败费用和归档。

## 当前实现

- Easy：每组16项；Normal：每组24项；三张 Hard 均采用新的36项双段委托。
- Hard 的两段相互独立；部分资料要求编目再核验。24种基础经验各2次单独使用、2次组合使用，组合前已在普通计分任务中遇到两项基础操作。三张地图逐张评估，地形与站点能力保持原样。详见 [Hard36](docs/HARD36.md)。
- 单步与连续移动均由 Hermes 自己选择动作；连续移动一次最多32个相邻地点，每一步照常计步、计路程。当前授权的 Hard 固定单步。
- 实验列表旁的「新建实验」打开当前页弹窗，选择模型、地图与移动方式后同时启动 retain／clear，预算在「运行设置」中展开。服务器独立处理额度等待、同请求重试、重启接续、严格审计和归档；关闭网页不会终止任务。
- `config/model-gateways.json` 固定真实路由上下文：Luna／Terra272000，当前 Gemini 网关250000；模型原生容量与网关限制分开记录。未知模型拒绝启动。

Lunatic 方案暂缓。已撤回的规则迁移与旧实验入口不会自动恢复。按用户2026-11-15最新纠正，64k时期全部实验结果作废并清理，包含旧Gemini和先前保留的四份单步参照。保留当前大上下文实验及共享依赖；当前没有有效的既有单步参照，不再引用64k成绩。

## 本地游玩与服务器配置

Python3.10+，游戏核心无第三方依赖：

```powershell
python -m memorybenchmark
```

实验创建需服务器的 `config/experiment-runtime.json`；使用已提供的 example 设置固定路径并启用。原生 Hermes 运行需既有 WSL／固定版本 MCP 环境。凭据只留在服务器加密存储或网关连接文件，不放入网页或仓库。生产入口保留原 PIN 和 HTTPS。

## 目录

| 目录 | 内容 |
| --- | --- |
| `memorybenchmark/prototypes/` | 游戏、任务状态、经验计数与原生交互 |
| `memorybenchmark/experiments/` | 成对创建、冻结源码、调度、运行、恢复、归档与费用 |
| `memorybenchmark/transports/` | Gemini Chat与精确订阅错误适配 |
| `memorybenchmark/data/` | 当前地图；history只保留读取测试所需配置夹具 |
| `memorybenchmark/static/` | 地图、游玩、实验记录及新建实验弹窗 |
| `config/` | 上下文、存储、服务器路径、Hard36分配与授权批次 |
| `scripts/`、`tests/` | 可复用制作／部署／审计工具及行为合同 |
| `docs/` | 当前协议与运行说明 |
| `references/` | 参照有效性说明；旧64k参照已撤销 |
| `.runs/` | Gemini与本次操作回执；不是源码依赖 |

新实验在服务器私有根的 `experiments/<pair-id>/<condition>` 下保存；不再用一批临时脚本管理每个实验。完整历史使用压缩事件块，模型参数只保存一次，共享只读原生源码。归档逐项验证后移除已证明重复的展开模型记录，保留可恢复清单、完整ZIP及公开结果。

## 验证与文档

```powershell
python -m pip install -e ".[mcp,test]"
python -m unittest discover -s tests
```

[实验配置与生命周期](docs/EXPERIMENTS.md) · [代码规范](docs/CODE_STYLE.md) · [Hard36](docs/HARD36.md)
