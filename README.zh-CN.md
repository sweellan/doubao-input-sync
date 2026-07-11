# Doubao Input Sync

把手机端输入，变成桌面端可接收的文本。

`Doubao Input Sync` 是一个很轻量的本地桥接工具：你可以在手机浏览器里输入或粘贴一大段文字，既可以停顿后自动发送，也可以打开“换气模式”，等完整说完再手动发送；如果你愿意，还可以直接把最终文本自动粘贴到 macOS 当前光标所在的位置。

这是一个非官方工具，只负责桥接输入结果，不隶属于豆包或其输入法产品团队。

先打个预防针：这更像一个实用主义的小工具，而不是打磨完整的正式产品。我也不是专业开发者，安装过程和边缘情况可能还会有点糙 🙈。很多时候，最省心的方式反而是直接交给你的 coding agent 帮你跑和微调。

English documentation: [README.md](README.md)

## 这个项目解决什么问题

有些输入体验在手机端很好用，但桌面端没有同样方便的入口。这个项目并不试图重做输入法本身，而是只桥接“输入结果”：

- 手机端固定输入区
- 本地 relay server
- 桌面端监看页
- 可选的 macOS 自动粘贴 helper

## 功能特点

- 两种可随时切换的发送节奏：`⚡ 顺口模式`停顿后自动发送，`🌿 换气模式`允许任意长停顿、只在点击后发送
- 顺口模式默认要等输入内容连续约 `2` 秒都没有新变化，才会正式捕捉
- 换气模式仍会持续保存草稿，刷新页面不必从头再说；点击“说完了，发送”后立即进入归档与自动粘贴链路
- 默认使用随机 pairing code，而不是固定共享的房间名
- 同一个房间里强约束为 `1 个手机位 + 1 个 PC 位`，冲突时会提示
- 同一 room 的手机端和 PC 端同步页面底色，便于区分不同电脑
- 桌面端保留历史列表，每条都可单独复制
- 可选自动粘贴到当前激活输入框
- Python 端只用标准库，没有额外依赖
- 手机不在局域网时，可临时通过 tunnel 做公网测试
- 当一批稳定文本被捕捉并同步后，界面会轻微闪一下做提示
- 如果公网 tunnel 下 SSE 重连不稳定，会自动退回轮询兜底

## 工作方式

```text
手机浏览器
  -> POST /api/update
本地 Python relay
  -> 维护房间状态
  -> 通过 SSE 推送给桌面页
  -> 顺口模式：输入稳定后自动归档
  -> 换气模式：点击发送后立即归档
macOS helper
  -> 监听最新归档项
  -> 复制或粘贴到当前应用
```

## 目录结构

```text
app/
  server.py          # 本地 relay server
  static/            # 手机页 + 桌面页
scripts/
  run_local_server.sh
  run_autopaste_local.sh
  run_tunnelmole.sh
  run_helper_daemon.sh
  install_launch_agent.sh
  uninstall_launch_agent.sh
  launch_agent_status.sh
  start_tmux_helper.sh
  stop_tmux_helper.sh
  mac_paste_helper.py
  smoke_test.py
docs/
  REMOTE_TAILSCALE_RELAY.md
  OPERATIONS.md
```

## 快速开始

### 1. 启动本地 relay server

```bash
./scripts/run_local_server.sh
```

默认地址是 `http://127.0.0.1:18766`。

### 2. 打开手机输入页

如果手机和电脑在同一个局域网：

```text
http://<你的电脑局域网IP>:18766/mobile/doubao
```

如果手机只能走公网，先起一个临时 tunnel：

```bash
./scripts/run_tunnelmole.sh
```

然后用输出的 HTTPS 地址再拼上 `/mobile/doubao`。

### 3. 打开桌面监看页

```text
http://127.0.0.1:18766/pc/doubao
```

### 4. 可选：直接自动粘贴到当前光标位置

```bash
./scripts/run_autopaste_local.sh
```

这条命令会：

- 如果本地 relay 没起，就先帮你拉起
- 监听最新归档结果
- 在 macOS 上把这条稳定文本自动粘贴到当前焦点输入框

## 选择你的输入节奏

手机输入框上方紧贴着两个模式按钮：

- `⚡ 顺口模式`：和原来一样，停顿达到等待时间后自动发送。适合连续口述或短句输入。
- `🌿 换气模式`：可以换气、阅读、思考，停多久都不会自动发送。完整说完后点旁边的“说完了，发送”，这批文字会立即交给电脑。

模式以 room 的服务端状态为准，同一页面刷新后仍会保持；relay 重启后则安全回到顺口模式。切回顺口模式时，当前草稿会重新进入按秒数自动发送的计时。

## 复用固定 tunnel 入口

如果你已经有一个固定公网 tunnel 域名，而且它当前正指向别的本地服务，最现实的免新域名方案通常是：

```text
固定公网 tunnel 域名
  -> 宿主机本地反向代理
     -> /doubao/* 转给 Doubao Input Sync
     -> 其他路径继续转给现有本地服务
```

这个仓库现在已经支持挂在子路径下，比如 `/doubao`，不再要求独占根路径 `/`。

以子路径模式启动：

```bash
BASE_PATH=/doubao ./scripts/run_local_server.sh --host 127.0.0.1 --port 18766
```

然后在宿主机前面放一个本地反向代理。仓库里附了一个 Caddy 示例配置：
[`deploy/Caddyfile.ngrok-subpath.example`](deploy/Caddyfile.ngrok-subpath.example)

一个典型落地方式是：

- 现有本地服务继续留在 `127.0.0.1:18789`
- Doubao Input Sync 跑在 `127.0.0.1:18766`，并设置 `BASE_PATH=/doubao`
- Caddy 监听 `127.0.0.1:18889`
- 把固定 tunnel 的上游从 `127.0.0.1:18789` 改成 `127.0.0.1:18889`

这样最终访问地址就是：

- 手机页：`https://<固定域名>/doubao/mobile/<room>`
- PC 页：`https://<固定域名>/doubao/pc/<room>`

和继续追求“第二个长期免费的固定公网域名”相比，这条路通常更稳，也更容易长期维护。

## 常用命令

日常排障和调整先看：

[`docs/OPERATIONS.md`](docs/OPERATIONS.md)

只启动 relay：

```bash
./scripts/run_local_server.sh
```

启动 relay + 自动粘贴：

```bash
./scripts/run_autopaste_local.sh
```

默认会生成一个类似 `pair-a1b2c3` 的随机房间号，并打印对应的手机访问地址。

安全 dry-run：

```bash
MODE=clipboard ./scripts/run_autopaste_local.sh --dry-run
```

起临时公网 tunnel：

```bash
./scripts/run_tunnelmole.sh
```

跑自动 smoke test：

```bash
python3 scripts/smoke_test.py --room-id smoke-room --output-json /tmp/doubao-smoke.json
```

如果某个输入法会先出一版字、再快速修订一版，可以把归档等待窗口调大：

```bash
ARCHIVE_IDLE_SECONDS=3.2 ./scripts/run_autopaste_local.sh
```

现在手机页里也可以直接在界面上改这个等待时间。
顺口模式的逻辑不是“每隔 X 秒抓一次”，而是典型的 debounce：只要有新输入，计时就会重新开始；必须完整安静一段时间以后，才会正式捕捉。换气模式不受这个时间影响。

## 数据隔离

别人 `clone` 下去以后，默认不会和你的数据存档互相打架。

原因是当前状态和历史都只保存在各自本地进程的内存里。不同机器、不同本地实例天然隔离。只有在多个客户端故意连到同一个 relay server、并且还使用同一个 `room_id` 时，数据才会混到一起。

手机页里也有一个 `归档后自动清空` 选项，而且现在默认就是勾选的。你如果更想人工确认，就把它关掉，继续手动点清空。

## 配对规则

每个 room 默认只允许：

- 1 个手机位
- 1 个 PC 位

如果另一台手机或另一台 PC 试图占用同一个 room 的同一角色，页面会直接提示冲突，并建议切换到新的 room id。

## tunnel 怎么常驻

临时 tunnel 适合试跑，但稳定性一般。

如果要常驻，比较靠谱的几条路是：

- 用 `cloudflared tunnel` 做 named tunnel，再配 macOS `launchd`
- 用 `ngrok` 登录账号后保留一个固定入口
- 自己准备一个小 VPS / 反向代理做长期转发

如果只是临时演示，`tunnelmole` 还够用；如果想日常稳定用，下一步最值得做的是 `cloudflared + launchd`。

## 远端 relay 模式

如果手机输入页已经放在远端 Linux relay 上，而这台 Mac 只需要通过 Tailscale 去消费远端 relay，请看 [docs/REMOTE_TAILSCALE_RELAY.md](docs/REMOTE_TAILSCALE_RELAY.md)。

## 不开 Terminal 也能跑

如果你是直接在 Terminal 里执行 helper，那这个 Terminal 窗口必须一直活着。

更适合长期使用的方式，是给当前用户安装一个 macOS LaunchAgent：

```bash
SERVER_URL="https://openclaw.ciaobella.cc/doubao" \
ROOM_ID="testroom" \
MODE="paste" \
./scripts/install_launch_agent.sh
```

后续常用命令：

```bash
./scripts/launch_agent_status.sh
./scripts/uninstall_launch_agent.sh
```

如果你更想用“前台 helper + tmux 常驻”的方式，也可以：

```bash
./scripts/start_tmux_helper.sh
tmux attach -t doubao-paste
```

## macOS 权限

自动粘贴依赖 `Accessibility` 权限。你需要给运行 helper 的宿主程序授权，比如 Terminal 或 Codex。

如果没授权：

- relay 仍然可以工作
- 桌面监看页仍然可以工作
- 剪贴板模式仍然可以工作
- 直接粘贴可能失败或者没有反应

## 公网测试

仓库里附带了一个 [Tunnelmole](https://tunnelmole.com/) 启动脚本，因为它可以直接通过 `npx` 快速拉起，适合临时测试。

安全建议：

- 做临时公网测试时，尽量使用随机 room id
- tunnel 用完就关，不要长期开着
- 服务端当前只做内存态存储
- 停掉 server 后，历史列表会清空

## 当前限制

- 直接自动输入目前主要面向 macOS
- 历史列表目前只在内存里，不会持久化到磁盘
- 还没有认证层
- 不适合直接拿去做多人生产环境服务

## 开发检查

不需要构建。

常用检查命令：

```bash
python3 -m py_compile app/server.py scripts/mac_paste_helper.py scripts/smoke_test.py
node --check app/static/client.js
python3 scripts/smoke_test.py --room-id smoke-room --output-json /tmp/doubao-smoke.json
python3 scripts/smoke_test.py --room-id smoke-room --base-path /doubao --output-json /tmp/doubao-smoke-subpath.json
```

## 许可证

MIT
