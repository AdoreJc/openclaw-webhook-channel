---
name: openclaw-webhook-channel
description: Configure and manage the OpenClaw Webhook Channel server — a lightweight Flask service that receives external webhooks and routes messages to OpenClaw chat channels (WeChat, Telegram, etc.) via `openclaw message send`. Use this skill when the user wants to set up, configure, debug, or extend the webhook channel, add new routes, or integrate external services (GitHub Actions, game automation, monitoring alerts) with OpenClaw messaging.
---

# OpenClaw Webhook Channel

通用 Webhook → OpenClaw 消息转发器。接收外部系统的 webhook 通知，转发到 OpenClaw 聊天渠道。

**必传 header：`channel` + `userId`**
**可选 header：`account`**（指定机器人账号，不传则从 config 取默认值）

## 项目位置

- 配置：`config.json`
- Python venv：`.venv/`

## 架构

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

## Header 参数

| Header | 必传 | 说明 | 示例 |
|--------|------|------|------|
| `channel` | ✅ | OpenClaw 渠道名 | `openclaw-weixin`、`telegram` |
| `userId` | ✅ | 目标用户 ID（同时作为 target） | `user@im.wechat`、`123456789` |
| `account` | ❌ | 机器人账号（不传则从 config channels 取） | `your-bot-id` |

## 两种模式

### Loose（默认）

`channel` + `userId` 必传，任意 userId 都允许发送。`account` 从 config channels 取默认值。

### Strict

`channel` + `userId` 必传，且 userId 必须在 `channels.<channel>.users` 列表中匹配到才发送。不匹配返回 403。

```json
{
  "mode": "strict",
  "channels": {
    "telegram": {
      "account": "default",
      "users": ["123456789"]
    }
  }
}
```

## config.json 结构

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

### channels 配置

| 字段 | 必填 | 说明 |
|------|------|------|
| `account` | ✅ | 该渠道发送时使用的 bot 账号（默认值，可被 header 覆盖） |
| `users` | ❌ | strict 模式下允许的 userId 列表 |

### routes 配置

路由定义消息模板，`{{message}}` 必填，其他字段从请求体取。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/webhook/<route_id>` | 按路由模板转发 |
| POST | `/webhook/generic` | 直通，无模板 |
| GET | `/health` | 健康检查 |

## 集成示例：AUTO-MAS

**URL：** `http://<WSL网关IP>:9876/webhook/arknights`

**Headers：**
| Key | Value |
|-----|-------|
| Content-Type | application/json |
| channel | openclaw-weixin（或 telegram） |
| userId | 你的用户 ID |

**Body：**
```json
{"message": "{title}: {content}", "timestamp": "{datetime}"}
```

WSL 网关 IP：`ip route show default | awk '/default/ {print $3}'`

## 启动与管理

```bash
cd /mnt/e/repos/openclaw-webhook-channel
.venv/bin/python webhook_server.py
```

## 常见问题

**HTTP 400: Missing required header: channel**
必传 header `channel` 缺失。

**HTTP 400: Missing required header: userId**
必传 header `userId` 缺失。

**HTTP 400: Unknown channel: xxx**
config.json 的 `channels` 中没有对应渠道配置。

**HTTP 403: userId not allowed**
strict 模式下 userId 不在 `channels.<channel>.users` 列表中。

**HTTP 500: Failed to send via OpenClaw**
`openclaw message send` 失败，检查渠道状态：`openclaw channels status`
