# Squishy 部署与网页观测

部署日期：2026-10-16。服务运行在 Squishy 的 Windows 主机上，GA 隔离执行使用该主机的 WSL Ubuntu。

2026-10-20 统一 MCP 接入：正式 agent 入口为 `memorybenchmark.experiment --agent ga`，GA 使用宿主的 MCP 客户端连接共用服务；内存传输不新增网络端口，网页仍为 8765。标准 stdio MCP 另用于单任务试玩。安装官方 SDK 的固定版本使用 `python -m pip install -e ".[mcp]"`；服务器将其放在仓库 `.venv`，`start_ga.ps1` 优先使用该环境，也可通过 `-Python` 显式指定。WSL 内的原生 GA 依赖不变。新运行写入 `.runs/agent-cross-session`，默认观测台兼容新旧目录；恢复旧实验仍使用冻结的直接 RPC。

2026-10-19 更新：[雾汀湖 Easy](EASY_LAKE.md) 为默认游玩场景 `lake-easy`，提供 31 个地点和 8 项委托，参考风险次数为 1、2、1、2、2、2、2、2。任务、观察、界面和背景图使用虚构命名。Agent 与人类都能看到已提交的纯地理图，经验记忆仍由 Agent 自主保存。`start_ga.ps1` 默认选用 T1–T8，48 轮任务预算、6 轮整理预算；部署不自动启动模型实验。

当前规则为 `lake-easy-3.0`：体力耗尽后在本项出发营地复活，恢复初始体力、清空工具，保留测绘进度与全部已发生的代价，游戏操作和模型调用预算不重置。轨迹额外生成死亡地点到营地的 `respawn` 有向边，默认权重 70、耗时 1，可在地图配置中调整；普通路程和复活惩罚分开统计。网页用红色虚线显示复活边，共享地理图不将其当作道路。旧实验沿用冻结的原始规则。

3.0 版已部署并验收：Squishy 的 74 项测试全部通过，八项参考路线零死亡重放成功。公网沿用有效 TLS 与 PIN 鉴权，验证了 T2 致死动作后的 `P1 → C0` 复活（权重 70、同任务运行 ID、操作数不重置）、相同请求重发不重复计数、死亡后成功提交、复活边不进入地理道路图、T3 开始后复活计数与历史清零、两组旧实验可读和退出后 401。本地浏览器验证了红色复活边、复活后补取工具继续提交与新委托重置，控制台无错误。没有启动新的模型实验。

v1 的 61 项测试、2.0 四任务版和 2.1 八任务版的验收均为历史记录。

2026-10-20 新 GA 提示协议保留明确的任务前检查与任务末尾复盘要求，当前任务直接显示在每步文字反馈中，每次模型请求附带两行简短委托提示，不再生成 `current_task.md`。新运行记录 `cartography-native-memory-3`，旧运行按冻结协议恢复。本地 80 项测试通过 79 项、权限跳过 1 项；真实 GA 离线契约检查使用脚本响应，覆盖实际历史裁剪、无任务文件的委托提示、原生整理工具读取规范、清除与回滚。没有启动新的真实模型实验，`MemorybenchmarkGA` 保持按需待命。

2.0 版历史验收：Squishy 的 63 项测试全部通过，四项参考路线在真实规则引擎重放通过；公网鉴权、共享地理图、回营提交与失败后的任务接续均通过。旧实验保留其原始配置。

2.1 八任务版历史验收：Squishy 的 66 项测试全部通过，八项参考路线重放成功。公网有效 TLS、PIN 与 Secure Cookie、`/design` 及资源访问、31 地点／31 通路、两组触发点的任务关联、查看前后游戏观察不变、Agent 不获得隐藏经验、旧实验读取和退出后 401 均通过接口验证。本地浏览器验证了桌面／手机布局、地图与委托切换、触发点开关和参考路线；该次没有启动新的模型实验。

## 地址与端口映射

将内网穿透的本地目标设为 **`127.0.0.1:8765`**，本地服务直接提供 HTTPS。Sakura 使用 **TCP 隧道，“自动 HTTPS”禁用**，原样转发 TLS 流量。

| 路径 | 用途 |
| --- | --- |
| `/` 或 `/watch` | 实验观测台，自动跟随正在运行的 GA |
| `/play` | 人类游玩界面，使用独立游戏实例 |
| `/design` | 当前地图完成图、经验触发点与委托参考路线，只供人查看 |
| `/api/design?scenario=lake-easy` | 只读设计投影，沿用 PIN 鉴权，不进入 Agent 游戏协议 |
| `/health` | 服务健康检查 |
| `/api/watch/runs` | 只读实验列表 |
| `/api/watch/run?id=实验编号` | 只读实验快照 |

公网入口位于节点 `frp-fee.com`，地址为 `https://s.roundsquisheen.v6.navy:43821/`。TLS 由 benchmark 程序处理，与 Claude Code 的方式一致；服务只监听回环地址，不需要开放 Windows 入站 8765 端口。

切换完成（2026-10-18）：原生 HTTPS 服务已启动，回环地址与公网的域名证书校验均通过。benchmark 隧道（ID `29544764`）已关闭自动 HTTPS 并加载新配置，只做 TCP 转发；本地／远程端口保持 `8765`／`43821`，其他隧道配置未修改。

页面现使用 PIN 登录。未登录时，观测台、游玩页、静态资源和所有接口均不可读取；接口返回 401，页面转到 `/login`。登录使用 HttpOnly、Secure、SameSite=Strict 的 Cookie，12 小时后过期，退出后立即撤销，重启服务也会注销现有会话。5 次错误尝试后至少冷却 60 秒，限速不信任访问者自行提供的 IP 头。跨站登录、操作与退出请求被拒绝。

`%LOCALAPPDATA%\Memorybenchmark\web-auth.json` 仅保存 scrypt 加盐哈希，不保存原始 PIN。后台脚本必须读到有效鉴权配置才会启动。更改 PIN 时在服务器执行以下命令，在隐藏输入提示中填写新 PIN，然后重启网页任务：

```powershell
python -m memorybenchmark.web_auth "$env:LOCALAPPDATA\Memorybenchmark\web-auth.json" --replace
powershell -NoProfile -File scripts/restart_watch.ps1
```

benchmark 直接读取 Claude Code 已有的证书源文件：`C:\Agents\ClaudeCode\Boss\claude-web\data\tls\cert.pem` 与同目录 `key.pem`。不修改源文件，不另外申请证书。原有续期任务更新这些文件后，benchmark 最多约 60 秒自动加载新证书；新连接使用新证书，已有登录和游戏实例保留。若文件更新不完整或证书与私钥不匹配，继续使用上一份有效证书，并在后续检查中重试。

启动时证书缺失或无效会直接报错，不会回退到明文 HTTP。之前在 Sakura 工作目录准备的证书副本不再被 benchmark 使用，也不需要随续期同步。

原生 HTTPS 切换后的公网验证全部通过：登录页返回 200；未登录的实验接口返回 401；使用指定 PIN 后获得 Secure Cookie，可读取两组历史实验，访问观测台、游玩页及其脚本；退出后实验接口再次返回 401。验证全程使用正常的 TLS 证书校验。本机浏览器此前也已完成错误提示、正确 PIN 登录与退出验证。

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

更新后重启使用 `powershell -NoProfile -File scripts/restart_watch.ps1`。Windows 停止启动壳时可能留下 Python 子进程；该脚本只清理 8765 端口上经命令行校验的 benchmark 监听进程，其他程序占用时会报错，不会误杀，然后启动原有计划任务。

也可在仓库根目录前台启动，用于排查服务问题；已有后台服务时先停止它，避免端口冲突：

```powershell
powershell -NoProfile -File scripts/restart_watch.ps1 -StopOnly
powershell -NoProfile -File scripts/start_watch.ps1 -Port 8765 `
  -TlsCert "C:\Agents\ClaudeCode\Boss\claude-web\data\tls\cert.pem" `
  -TlsKey "C:\Agents\ClaudeCode\Boss\claude-web\data\tls\key.pem"
```

`MemorybenchmarkGA` 为按需运行任务，不随开机自动反复调用模型。仅当需要开启一轮新实验，且当前没有 GA 正在执行时使用：

```powershell
Start-ScheduledTask -TaskName MemorybenchmarkGA
```

这个任务使用已配置的网关与 `gpt-5.6-luna` 别名。当前默认场景为 `lake-easy`，T1–T8、48 轮任务预算与 6 轮任务后整理预算；一个新实验包含 1 个公共前缀和 7 对保留／恢复基线条件，共 15 个有效会话。此前 T1–T6 的 11 会话记录属于旧 `valley` 场景。模型别名不独立证明底层模型身份。

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

迁移时运行了原生 GA 工具、记忆保留／恢复和基础设施失败回滚契约检查。Squishy 的 49 项单元测试全部通过，覆盖鉴权、原生 HTTPS、真实证书轮换、更新中断、空闲／明文连接隔离和既有游戏功能。本机 Windows 同套测试因权限跳过软链接创建一项。测试证书临时生成，不使用实际服务私钥；只有测试需要 OpenSSL，游戏运行仍只依赖标准库。浏览器验证了实时更新、历史选择、逐动作回放，以及桌面／手机布局。此处验证的是软件执行与观测链路，正式记忆效果仍按实验设计评估。
