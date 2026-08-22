# OpenClaw Webhook Channel

通用 Webhook → OpenClaw 消息转发器。接收外部系统的 webhook 通知，自动路由到对应的聊天联系人。

**纯自动化转发，不经过 LLM 处理。** 支持任意 webhook 来源：游戏自动化、GitHub Actions、CI/CD、监控告警等。

## 工作原理

```
外部系统 (Auto_MAS / GitHub / 监控 / ...)
  │  POST /webhook/<route_id>
  │  Header: userId = "user1"
  ▼
Webhook Server (WSL/Linux)
  │  1. 查路由模板 → 格式化消息
  │  2. 查 userId → WeChat/Telegram target
  │  3. 调用 openclaw message send
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
  "host": "0.0.0.0",
  "port": 9876,
  "users": {
    "user1": {
      "channel": "openclaw-weixin",
      "account": "your-bot-account-id",
      "target": "target-user-id@im.wechat"
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

在外部系统中设置 webhook URL：

- **URL**: `http://<WSL_IP>:9876/webhook/<route_id>`
- **Method**: POST
- **Headers**: `Content-Type: application/json`, `userId: <对应 user key>`

WSL2 IP：
```bash
ip route show default | awk '/default/ {print $3}'
```

## API

### POST `/webhook/<route_id>` — 通用路由端点

根据 route_id 匹配路由配置，应用消息模板后转发。

**请求头：**
- `userId` (必填): 用户标识

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
{"status": "ok", "users": ["user1"], "routes": ["arknights", "github"]}
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

## 内置快捷路由

| 路径 | 说明 |
|------|------|
| `/webhook/arknights` | → `routes.arknights` |
| `/webhook/github` | → `routes.github` |
| `/webhook/generic` | 直通，无模板 |

## 部署

### systemd 服务

```bash
sudo cp systemd/openclaw-webhook-channel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now openclaw-webhook-channel
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `OPENCLAW_WEBHOOK_CONFIG` | 配置文件路径 |
| `OPENCLAW_WEBHOOK_PORT` | 监听端口 |
| `OPENCLAW_WEBHOOK_HOST` | 监听地址 |

## 使用示例

### Auto_MAS 明日方舟

```bash
curl -X POST http://localhost:9876/webhook/arknights \
  -H "Content-Type: application/json" \
  -H "userId: user1" \
  -d '{"message": "理智已耗尽，自动刷图完成", "account": "主号"}'
```

### GitHub Actions

```bash
curl -X POST http://localhost:9876/webhook/github \
  -H "Content-Type: application/json" \
  -H "userId: user1" \
  -d '{"message": "Build #123 成功", "extra": {"repo": "my-project", "branch": "main"}}'
```

### 监控告警

```bash
curl -X POST http://localhost:9876/webhook/monitor \
  -H "Content-Type: application/json" \
  -H "userId: user1" \
  -d '{"message": "CPU 使用率超过 90%", "level": "warn"}'
```

## License

MIT
