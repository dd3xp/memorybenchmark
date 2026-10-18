# Squishy 部署与网页观测

部署日期：2026-10-16。服务运行在 Squishy 的 Windows 主机上，GA 隔离执行使用该主机的 WSL Ubuntu。

## 地址与端口映射

将内网穿透的本地目标设为 **`127.0.0.1:8765`**，本地服务直接提供 HTTPS。Sakura 使用 **TCP 隧道，“自动 HTTPS”禁用**，原样转发 TLS 流量。

| 路径 | 用途 |
| --- | --- |
| `/` 或 `/watch` | 实验观测台，自动跟随正在运行的 GA |
| `/play` | 人类游玩界面，使用独立游戏实例 |
| `/health` | 服务健康检查 |
| `/api/watch/runs` | 只读实验列表 |
| `/api/watch/run?id=实验编号` | 只读实验快照 |

公网入口位于节点 `frp-fee.com`，地址为 `https://s.roundsquisheen.v6.navy:43821/`。TLS 由 benchmark 程序处理，与 Claude Code 的方式一致；服务只监听回环地址，不需要开放 Windows 入站 8765 端口。

页面现使用 PIN 登录。未登录时，观测台、游玩页、静态资源和所有接口均不可读取；接口返回 401，页面转到 `/login`。登录使用 HttpOnly、Secure、SameSite=Strict 的 Cookie，12 小时后过期，退出后立即撤销，重启服务也会注销现有会话。5 次错误尝试后至少冷却 60 秒，限速不信任访问者自行提供的 IP 头。跨站登录、操作与退出请求被拒绝。

`%LOCALAPPDATA%\Memorybenchmark\web-auth.json` 仅保存 scrypt 加盐哈希，不保存原始 PIN。后台脚本必须读到有效鉴权配置才会启动。更改 PIN 时在服务器执行以下命令，在隐藏输入提示中填写新 PIN，然后重启网页任务：

```powershell
python -m memorybenchmark.web_auth "$env:LOCALAPPDATA\Memorybenchmark\web-auth.json" --replace
Stop-ScheduledTask -TaskName MemorybenchmarkWatch
Start-ScheduledTask -TaskName MemorybenchmarkWatch
```

benchmark 直接读取 Claude Code 已有的证书源文件：`C:\Agents\ClaudeCode\Boss\claude-web\data\tls\cert.pem` 与同目录 `key.pem`。不修改源文件，不另外申请证书。原有续期任务更新这些文件后，benchmark 最多约 60 秒自动加载新证书；新连接使用新证书，已有登录和游戏实例保留。若文件更新不完整或证书与私钥不匹配，继续使用上一份有效证书，并在后续检查中重试。

启动时证书缺失或无效会直接报错，不会回退到明文 HTTP。之前在 Sakura 工作目录准备的证书副本不再被 benchmark 使用，也不需要随续期同步。

公网已验证：证书校验通过；未登录的实验接口返回 401；使用指定 PIN 后，观测台、历史记录、游玩页和脚本均可访问；退出后实验接口再次返回 401。本机浏览器完成了错误提示、正确 PIN 登录与退出验证。没有关闭证书校验。

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
| `%LOCALAPPDATA%\Memorybenchmark\web-auth.json` | 网页 PIN 加盐哈希，仅当前用户与 SYSTEM 可读 |
| `C:\Agents\ClaudeCode\Boss\claude-web\data\tls\cert.pem`、`key.pem` | 现有域名证书源文件，benchmark 只读使用 |
| WSL `~/.local/share/memorybenchmark/runtime` | GA Python 运行环境 |

原始日志与第三方源码不通过网页提供，也不进入公开仓库。DPAPI 凭据绑定当前 Windows 用户，不能作为普通配置复制到其他账号或电脑；启动脚本仅在父进程中临时解密，Agent 沙箱接触不到它。

已迁入历史运行 `cdb03630ecb7490e8933490422d7facf`；新服务器联调运行编号为 `b5b879140a8e4166959c7f842dbd33c6`。这些编号可在网页选择器中找到。

新运行已完成 11 个有效会话，10 个成功、T1 到达目标后未提交，累计 63 次模型调用、25 条通勤边，没有基础设施失败或新增记忆文件。此结果验证迁移和观测功能，不作为记忆收益证据。

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
powershell -NoProfile -File scripts/start_watch.ps1 -Port 8765 `
  -TlsCert "C:\Agents\ClaudeCode\Boss\claude-web\data\tls\cert.pem" `
  -TlsKey "C:\Agents\ClaudeCode\Boss\claude-web\data\tls\key.pem"
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

迁移时运行了原生 GA 工具、记忆保留／恢复和基础设施失败回滚契约检查。49 项单元测试覆盖鉴权、原生 HTTPS、真实证书轮换、更新中断、空闲／明文连接隔离和既有游戏功能。测试证书临时生成，不使用实际服务私钥；只有测试需要 OpenSSL，游戏运行仍只依赖标准库。Windows 因权限跳过软链接创建一项。浏览器验证了实时更新、历史选择、逐动作回放，以及桌面／手机布局。此处验证的是软件执行与观测链路，正式记忆效果仍按实验设计评估。
