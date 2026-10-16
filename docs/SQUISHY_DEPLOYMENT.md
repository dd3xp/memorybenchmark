# Squishy 部署与网页观测

部署日期：2026-10-16。服务运行在 Squishy 的 Windows 主机上，GA 隔离执行使用该主机的 WSL Ubuntu。

## 地址与端口映射

将内网穿透的本地目标设为 **`127.0.0.1:8765`**，协议使用 HTTP。

| 路径 | 用途 |
| --- | --- |
| `/` 或 `/watch` | 实验观测台，自动跟随正在运行的 GA |
| `/play` | 人类游玩界面，使用独立游戏实例 |
| `/health` | 服务健康检查 |
| `/api/watch/runs` | 只读实验列表 |
| `/api/watch/run?id=实验编号` | 只读实验快照 |

外部端口、域名和 HTTPS 由用户的穿透服务决定。当前 HTTP 服务只监听回环地址，不需要开放 Windows 入站 8765 端口。现有穿透配置没有修改。观测页面没有登录机制；映射后可访问该地址的人能查看公开投影和游玩，需要限制访问时可在穿透入口设置认证。

观测台约每 1.5 秒更新一次，展示实际游戏反馈、Agent 已发现的地图、按顺序保留的通勤、体力、携带工具、模型调用状态与记忆文件变化。点击会话可查看其末尾，点击“回放”逐动作播放；“跟随运行”回到当前会话。运行选择器可切换已迁入的旧实验。

## 服务器目录

| 路径 | 内容 |
| --- | --- |
| `C:\Codes\memorybenchmark` | 项目仓库 |
| `C:\Codes\memorybenchmark\.runs\ga-cross-session` | 真实实验、检查点、原始记录和网页快照 |
| `C:\Codes\memorybenchmark\.runs\service\watch.log` | 网页服务日志 |
| `C:\Codes\memorybenchmark\.runs\service\ga.log` | GA 启动和执行日志 |
| `C:\Codes\memorybenchmark-private` | 第三方 GA 源码归档、部署包和迁移归档 |
| `%LOCALAPPDATA%\Memorybenchmark\gateway.dpapi` | 当前 Windows 用户加密的网关凭据 |
| WSL `~/.local/share/memorybenchmark/runtime` | GA Python 运行环境 |

原始日志与第三方源码不通过网页提供，也不进入公开仓库。DPAPI 凭据绑定当前 Windows 用户，不能作为普通配置复制到其他账号或电脑；启动脚本仅在父进程中临时解密，Agent 沙箱接触不到它。

已迁入历史运行 `cdb03630ecb7490e8933490422d7facf`；新服务器联调运行编号为 `b5b879140a8e4166959c7f842dbd33c6`。这些编号可在网页选择器中找到。

## 启动与恢复

在 Squishy PowerShell 中检查后台任务：

```powershell
Get-ScheduledTask -TaskName MemorybenchmarkWatch,MemorybenchmarkGA
```

`MemorybenchmarkWatch` 已启动，并在该 Windows 用户登录时自动启动。手动启动：

```powershell
Start-ScheduledTask -TaskName MemorybenchmarkWatch
```

也可在仓库根目录前台启动，用于排查服务问题；已有后台服务时先停止它，避免端口冲突：

```powershell
Stop-ScheduledTask -TaskName MemorybenchmarkWatch
powershell -NoProfile -File scripts/start_watch.ps1 -Port 8765
```

`MemorybenchmarkGA` 为按需运行任务，不随开机自动反复调用模型。仅当需要开启一轮新实验，且当前没有 GA 正在执行时使用：

```powershell
Start-ScheduledTask -TaskName MemorybenchmarkGA
```

这个任务使用已配置的网关、`gpt-5.6-luna` 别名、T1–T6、16 轮动作预算与 6 轮任务后整理预算。一个新实验包含 1 个公共前缀和 5 对保留／恢复基线条件，共 11 个有效会话。模型别名不独立证明底层模型身份。

网关等基础设施故障导致中断时，先确认原进程已经退出，再从原实验目录恢复，避免重跑已经完成的会话：

```powershell
powershell -NoProfile -File scripts/start_ga.ps1 `
  -BaseUrl "<原网关地址>" `
  -Resume ".runs/ga-cross-session/<实验编号>"
```

恢复沿用该运行冻结的任务、预算与模型协议。正常任务失败仍是有效结果；只有基础设施失败走检查点回滚。网页的“未完成”与“中断”分别表示这两类情况。

## 隔离与验证

网页是旁路投影：实验父进程将公开观察写入 `live.json`，观测服务读取它；人类游玩实例不共享实验世界。原始任务约束、未知危险、模型请求正文、记忆原文和凭据不进入观测 API。浏览网页不会增加模型调用，也不向 Agent 添加上下文。

服务器使用 Windows Python 3.13、WSL Ubuntu 24.04 与 bubblewrap。游戏和网页只依赖 Python 标准库，模型推理通过远端网关完成，不要求本地 GPU。当前机器有 i7-12700H 和约 32 GB 内存，足以承载当前单路 GA 联调与网页；扩大并发应根据实际测量设置上限。

迁移时运行了 37 项单元测试，以及原生 GA 工具、记忆保留／恢复和基础设施失败回滚契约检查。浏览器验证了实时更新、历史选择、逐动作回放，以及桌面／手机布局。此处验证的是软件执行与观测链路，正式记忆效果仍按实验设计评估。
