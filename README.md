# OpenClaw Webhook Channel

> **English** | [简体中文](README.zh-CN.md)

A lightweight webhook-to-chat relay for [OpenClaw](https://github.com/openclaw/openclaw). Receives HTTP webhooks from external systems and forwards messages to OpenClaw chat channels (WeChat, Telegram, etc.) via `openclaw message send`.

**Pure message forwarding — no LLM processing.** Supports any webhook source: game automation, GitHub Actions, CI/CD, monitoring alerts, and more.

## How It Works

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

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Make sure `openclaw` CLI is installed and the target channel is configured.

### 2. Configure

```bash
cp config.example.json config.json
```

Edit `config.json`:

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

### 3. Run

```bash
python webhook_server.py
```

### 4. Configure Webhook Sources

Set up webhook URL and headers in your external system:

- **URL**: `http://<host>:9876/webhook/<route_id>`
- **Method**: POST
- **Headers**: `Content-Type: application/json`, `channel: <channel-name>`, `userId: <user-id>`

For WSL2, use the gateway IP:
```bash
ip route show default | awk '/default/ {print $3}'
```

## Header Parameters

| Header | Required | Description | Example |
|--------|----------|-------------|---------|
| `channel` | ✅ | OpenClaw channel name | `openclaw-weixin`, `telegram` |
| `userId` | ✅ | Target user ID (also used as the message target) | `user@im.wechat`, `123456789` |
| `account` | ❌ | Bot account override (falls back to config) | `your-bot-id` |

## Two Modes

### Loose (default)

`channel` + `userId` required. Any userId is allowed to receive messages.

### Strict

`channel` + `userId` required. The userId must appear in `channels.<channel>.users` list. Returns 403 if not matched.

## API

### POST `/webhook/<route_id>` — Templated Endpoint

Matches the route config by `route_id`, applies the message template, then forwards.

**Headers:**
- `channel` (required): OpenClaw channel name
- `userId` (required): Target user ID
- `account` (optional): Bot account override

**Body (JSON):**
```json
{
  "message": "notification content",
  "level": "info",
  "extra": { "key": "value" }
}
```

### POST `/webhook/generic` — Pass-through Endpoint

No template — forwards the raw `message` field directly.

### GET `/health` — Health Check

```json
{"status": "ok", "mode": "loose", "channels": ["openclaw-weixin", "telegram"], "routes": ["arknights"]}
```

## Route Templates

`{{message}}` in the template is replaced with the actual message. Other fields from the request body work the same way:

```json
{
  "template": "🎮 {{message}} (account: {{account}})",
  "defaultLevel": "info"
}
```

Request body `{"message": "Out of sanity", "account": "Main"}` → Final message: `🎮 Out of sanity (account: Main)`

## Deployment

### systemd User Service (Recommended)

Uses `systemd --user` — no sudo required, auto-starts on boot:

```bash
# 1. Enable linger (service stays alive after logout in WSL)
loginctl enable-linger $(whoami)

# 2. Copy service file
mkdir -p ~/.config/systemd/user
cp systemd/openclaw-webhook-channel.service ~/.config/systemd/user/

# 3. Reload and start
systemctl --user daemon-reload
systemctl --user enable --now openclaw-webhook-channel

# 4. Check status / logs
systemctl --user status openclaw-webhook-channel
journalctl --user -u openclaw-webhook-channel -f
```

> ⚠️ Make sure `openclaw` CLI is in PATH (the service file sets `Environment=PATH` — adjust if your install path differs).

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENCLAW_WEBHOOK_CONFIG` | Config file path |
| `OPENCLAW_WEBHOOK_PORT` | Listen port |
| `OPENCLAW_WEBHOOK_HOST` | Listen address |

## Usage Examples

### Game Automation (AUTO-MAS)

```bash
curl -X POST http://localhost:9876/webhook/arknights \
  -H "Content-Type: application/json" \
  -H "channel: openclaw-weixin" \
  -H "userId: your-wechat-user-id@im.wechat" \
  -d '{"message": "Out of sanity, auto-farming complete"}'
```

### GitHub Actions

```bash
curl -X POST http://localhost:9876/webhook/github \
  -H "Content-Type: application/json" \
  -H "channel: telegram" \
  -H "userId: 123456789" \
  -d '{"message": "Build #123 succeeded", "extra": {"repo": "my-project", "branch": "main"}}'
```

### Monitoring Alerts

```bash
curl -X POST http://localhost:9876/webhook/monitor \
  -H "Content-Type: application/json" \
  -H "channel: telegram" \
  -H "userId: 123456789" \
  -d '{"message": "CPU usage above 90%", "level": "warn"}'
```

## License

MIT
