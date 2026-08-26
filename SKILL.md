---
name: openclaw-webhook-channel
description: Configure and manage the OpenClaw Webhook Channel server — a lightweight Flask service that receives external webhooks and routes messages to OpenClaw chat channels (WeChat, Telegram, etc.) via `openclaw message send`. Use this skill when the user wants to set up, configure, debug, or extend the webhook channel, add new routes, or integrate external services (GitHub Actions, game automation, monitoring alerts) with OpenClaw messaging.
---

# OpenClaw Webhook Channel

A lightweight webhook-to-chat relay for OpenClaw. Receives HTTP webhooks from external systems and forwards messages to OpenClaw chat channels.

**Required headers: `channel` + `userId`**
**Optional header: `account`** (bot account override; falls back to config default)

## Project Paths

- Config: `config.json`
- Python venv: `.venv/`

## Architecture

```
External System (GitHub / Monitoring / Game Bot / ...)
  │  POST /webhook/<route_id>
  │  Headers: channel + userId [+ account]
  ▼
Webhook Server (Flask, 127.0.0.1:9876)
  │  1. channel → resolve bot account from config (or use header)
  │  2. userId → used as target
  │  3. subprocess: openclaw message send
  ▼
OpenClaw Channel → Contact
```

## Header Parameters

| Header | Required | Description | Example |
|--------|----------|-------------|---------|
| `channel` | ✅ | OpenClaw channel name | `openclaw-weixin`, `telegram` |
| `userId` | ✅ | Target user ID (also used as the message target) | `user@im.wechat`, `123456789` |
| `account` | ❌ | Bot account override (falls back to config) | `your-bot-id` |

## Two Modes

### Loose (default)

`channel` + `userId` required. Any userId is allowed to receive messages. `account` falls back to the config default for the channel.

### Strict

`channel` + `userId` required. The userId must appear in `channels.<channel>.users` list. Returns 403 if not matched.

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

## config.json Structure

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

### channels Config

| Field | Required | Description |
|-------|----------|-------------|
| `account` | ✅ | Bot account used for this channel (default; can be overridden by header) |
| `users` | ❌ | Allowed userId list in strict mode |

### routes Config

Routes define message templates. `{{message}}` is required; other fields are taken from the request body.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhook/<route_id>` | Templated forwarding by route |
| POST | `/webhook/generic` | Pass-through, no template |
| GET | `/health` | Health check |

## Integration Example: AUTO-MAS

**URL:** `http://<host>:9876/webhook/arknights`

**Headers:**
| Key | Value |
|-----|-------|
| Content-Type | application/json |
| channel | openclaw-weixin (or telegram) |
| userId | your user ID |

**Body:**
```json
{"message": "{title}: {content}", "timestamp": "{datetime}"}
```

WSL gateway IP: `ip route show default | awk '/default/ {print $3}'`

## Running & Managing

```bash
cd /mnt/e/repos/openclaw-webhook-channel
.venv/bin/python webhook_server.py
```

### systemd Auto-start

The project ships with `systemd/openclaw-webhook-channel.service` (user service, no sudo needed):

```bash
# First-time setup
loginctl enable-linger $(whoami)
mkdir -p ~/.config/systemd/user
cp systemd/openclaw-webhook-channel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now openclaw-webhook-channel

# Day-to-day
systemctl --user status openclaw-webhook-channel
systemctl --user restart openclaw-webhook-channel
journalctl --user -u openclaw-webhook-channel -f
```

> Linger=yes ensures the service survives WSL restarts without requiring a manual login.

## Troubleshooting

**HTTP 400: Missing required header: channel**
The `channel` header is missing from the request.

**HTTP 400: Missing required header: userId**
The `userId` header is missing from the request.

**HTTP 400: Unknown channel: xxx**
The channel is not defined in `config.json` → `channels`.

**HTTP 403: userId not allowed**
In strict mode, the userId is not in the `channels.<channel>.users` list.

**HTTP 500: Failed to send via OpenClaw**
`openclaw message send` failed. Check channel status: `openclaw channels status`
