# GenericAgent 与 Hermes 适配

`memorybenchmark/agent_bridge.py` 是可单独复制到原生 Agent 进程的工具桥，仅依赖标准库，不导入地图、经验或评测代码。`game_action` 支持移动、取用、观察、等待、提交、放弃和读取公开观察；不做规划，不修改或代写记忆。

Hermes 使用现有注册接口：

```python
from tools.registry import registry
from toolsets import create_custom_toolset
from agent_bridge import GameTool, register_hermes
register_hermes(registry, create_custom_toolset, GameTool(rpc_to_runner))
# 将 cartography 加入原生 AIAgent 原有的 enabled_toolsets。
```

GenericAgent 在模型选择后注册，避免 `next_llm()` 重载 schema 时覆盖：

```python
import agentmain
from agent_loop import StepOutcome
from agent_bridge import GameTool, register_genericagent
agent = agentmain.GeneraticAgent()  # 原项目类名的实际拼写。
agent.next_llm(selected_backend)
register_genericagent(agentmain, agent, StepOutcome, GameTool(rpc_to_runner))
```

`rpc_to_runner` 在独立 Agent 进程中通过通信请求动作，运行器仅返回当前任务公开反馈。正式运行应沿用旧适配的隔离方式，使文件／Shell 工具无法读取游戏进程、完整地图和日志，并将游戏动作标记为不可并发。桥也会串行调用。原生文件、计算和记忆工具保留；收到 `done=true` 后仍可自行整理记忆并结束回复。

## 已验证与未验证的范围

- 核心、配置和桥接测试覆盖公开信息一致、体力、取用、自动测绘、幂等和工具参数边界。
- 本地 `scripts/check_native_contracts.py` 直接读取旧复现包中的 Hermes `ToolRegistry` 与 GenericAgent `BaseHandler` 源码，真实注册／分发契约检查已通过，不调用模型。
- `HTTPGameClient` 可绑定运行器已创建的实例用于本地开发；它没有文件或网络隔离能力，不能单独作为正式实验运行器。
- 之前提供的模型网关可访问且可列出模型；凭据未写入仓库，校准轨迹不由模型生成。

```powershell
python scripts/check_native_contracts.py reproducibility_package_upload/agents
```

第三方 Agent 源码和旧复现包不在公开仓库中，普通测试不依赖它们。上述契约检查本身不等于完整原生 Agent 已启动；另外已完成一次 GA 原生模型循环的单任务开发试跑，具体结果和限制见 [当前成果](../PROGRESS.md)。

已有原生 GA 依赖及归档时，可以使用有明确调用上限的开发脚本复现。凭据从 `MEMORYBENCH_GATEWAY_KEY` 进程环境变量读取：

```powershell
python scripts/native_ga_smoke.py reproducibility_package_upload/agents/GenericAgent_src.tar.xz --base-url https://your-model-gateway --max-turns 12
```

脚本使用新建的 `.runs/` 私有目录，排除归档中的旧记忆、临时文件和凭据配置，原生模型与工具循环按预算运行；模型别名和输出上限会写入运行清单。它没有正式隔离，不作为 benchmark 实验入口。

下一步联合验证原生会话、记忆快照和隔离启动器：每任务新 session，两条件提示和反思机会匹配；快照覆盖可检索历史、自建技能、长期文件和后台更新。后台写入结束后再快照。基础设施重试恢复双方状态，真实体力耗尽不能重试。完成这些控制前不发布 MEM/NOMEM 效果分数。
