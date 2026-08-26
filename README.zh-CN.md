# OpenClaw Webhook Channel

> [English](README.md) | **简体中文**

通用 Webhook → OpenClaw 消息转发器。接收外部系统的 webhook 通知，自动路由到对应的聊天联系人。

**纯自动化转发，不经过 LLM 处理。** 支持任意 webhook 来源：游戏自动化、GitHub Actions、CI/CD、监控告警等。

## 工作原理

```
外部系统 (AUTO-MAS / GitHub / 监控 / ...)
  │  POST /webhook/<route_id>
  │  Headers: channel + userId [+ account]
  ▼
Webhook Server (Flask, 127.0.0.1:9876)
  │  1. channel → 查 config 取 account（或用 header 传入的）
  │  2. userId → 作为 target
  │  3. subprocess: openclaw message send
  ▼
OpenClaw Channel → 联系人
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

确保 `openclaw` CLI 已安装且配置了目标通道。

### 2. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`：

```json
{
  "host": "127.0.0.1",
  "port": 9876,
  "mode": "loose",
  "channels": {
    "openclaw-weixin": {
      "account": "your-weixin-bot-account-id",
      "users": ["your-wechat-user-id@im.wechat"]
    },
    "telegram": {
      "account": "default",
      "users": ["your-telegram-chat-id"]
    }
  },
  "routes": {
    "arknights": {
      "template": "🎮 {{message}}",
      "defaultLevel": "info"
    }
  }
}
```

### 3. 启动

```bash
python webhook_server.py
```

### 4. 配置 Webhook 来源

在外部系统中设置 webhook URL 和 headers：

- **URL**: `http://<WSL_IP>:9876/webhook/<route_id>`
- **Method**: POST
- **Headers**: `Content-Type: application/json`, `channel: <渠道名>`, `userId: <用户ID>`

WSL2 IP：
```bash
ip route show default | awk '/default/ {print $3}'
```

## Header 参数

| Header | 必传 | 说明 | 示例 |
|--------|------|------|------|
| `channel` | ✅ | OpenClaw 渠道名 | `openclaw-weixin`、`telegram` |
| `userId` | ✅ | 目标用户 ID（同时作为 target） | `user@im.wechat`、`123456789` |
| `account` | ❌ | 机器人账号（不传则从 config channels 取） | `your-bot-id` |

## 两种模式

### Loose（默认）

`channel` + `userId` 必传，任意 userId 都允许发送。

### Strict

`channel` + `userId` 必传，且 userId 必须在 `channels.<channel>.users` 列表中。不匹配返回 403。

## API

### POST `/webhook/<route_id>` — 通用路由端点

根据 route_id 匹配路由配置，应用消息模板后转发。

**请求头：**
- `channel` (必填): OpenClaw 渠道名
- `userId` (必填): 目标用户 ID
- `account` (可选): 机器人账号

**请求体 (JSON)：**
```json
{
  "message": "通知内容",
  "level": "info",
  "extra": { "key": "value" }
}
```

### POST `/webhook/generic` — 直通端点

无模板，直接转发 message。

### GET `/health` — 健康检查

```json
{"status": "ok", "mode": "loose", "channels": ["openclaw-weixin", "telegram"], "routes": ["arknights"]}
```

## 路由模板

模板中 `{{message}}` 会被替换为实际消息，其他字段同理：

```json
{
  "template": "🎮 {{message}} (账号: {{account}})",
  "defaultLevel": "info"
}
```

请求体 `{"message": "理智耗尽", "account": "主号"}` → 最终消息：`🎮 理智耗尽 (账号: 主号)`

## 部署

### systemd 用户服务（推荐）

使用 `systemd --user`，无需 sudo，开机自启：

```bash
# 1. 启用 linger（WSL 重启后不需要登录也能自启服务）
loginctl enable-linger $(whoami)

# 2. 复制 service 文件到用户 systemd 目录
mkdir -p ~/.config/systemd/user
cp systemd/openclaw-webhook-channel.service ~/.config/systemd/user/

# 3. 重载并启动
systemctl --user daemon-reload
systemctl --user enable --now openclaw-webhook-channel

# 4. 查看状态 / 日志
systemctl --user status openclaw-webhook-channel
journalctl --user -u openclaw-webhook-channel -f
```

> ⚠️ 确保 `openclaw` CLI 在 PATH 中（service 文件已配置 `Environment=PATH`，若安装路径不同需调整）。

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENCLAW_WEBHOOK_CONFIG` | 配置文件路径 |
| `OPENCLAW_WEBHOOK_PORT` | 监听端口 |
| `OPENCLAW_WEBHOOK_HOST` | 监听地址 |

## 使用示例

### AUTO-MAS 明日方舟

```bash
curl -X POST http://localhost:9876/webhook/arknights \
  -H "Content-Type: application/json" \
  -H "channel: openclaw-weixin" \
  -H "userId: your-wechat-user-id@im.wechat" \
  -d '{"message": "理智已耗尽，自动刷图完成"}'
```

### GitHub Actions

```bash
curl -X POST http://localhost:9876/webhook/github \
  -H "Content-Type: application/json" \
  -H "channel: telegram" \
  -H "userId: 123456789" \
  -d '{"message": "Build #123 成功", "extra": {"repo": "my-project", "branch": "main"}}'
```

### 监控告警

```bash
curl -X POST http://localhost:9876/webhook/monitor \
  -H "Content-Type: application/json" \
  -H "channel: telegram" \
  -H "userId: 123456789" \
  -d '{"message": "CPU 使用率超过 90%", "level": "warn"}'
```

## License

MIT
