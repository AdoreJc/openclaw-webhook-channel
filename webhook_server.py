#!/usr/bin/env python3
"""
OpenClaw Webhook Channel — 通用 Webhook → OpenClaw 消息转发器

接收外部系统的 webhook 通知，转发到 OpenClaw 聊天渠道。

必传 header：channel + userId
可选 header：account（指定机器人账号，不传则从 config channels 取）
userId 同时作为 target

两种模式：
  - loose（默认）：channel + userId 必传，任意 userId
  - strict：必须在 channels.<channel>.users 中匹配到 userId 才发送

用法:
    python webhook_server.py                    # 使用默认配置
    python webhook_server.py -c config.json     # 指定配置文件
    python webhook_server.py -p 9876            # 指定端口
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, abort, request, jsonify

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("openclaw-webhook-channel")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CONFIG: dict = {}
CHANNEL_MAP: dict = {}
ROUTE_MAP: dict = {}
MODE: str = "loose"


def load_config(path: str | None = None):
    """加载配置文件。"""
    global CONFIG, CHANNEL_MAP, ROUTE_MAP, MODE

    candidates = [
        path,
        os.environ.get("OPENCLAW_WEBHOOK_CONFIG"),
        os.path.join(os.path.dirname(__file__), "config.json"),
    ]
    for p in candidates:
        if p and Path(p).is_file():
            with open(p, encoding="utf-8") as f:
                CONFIG = json.load(f)
            log.info("Loaded config from %s", p)
            break
    else:
        log.warning("No config file found, using defaults")
        CONFIG = {}

    CHANNEL_MAP = CONFIG.get("channels", {})
    ROUTE_MAP = CONFIG.get("routes", {})
    MODE = CONFIG.get("mode", "loose")

    if port := os.environ.get("OPENCLAW_WEBHOOK_PORT"):
        CONFIG["port"] = int(port)
    if host := os.environ.get("OPENCLAW_WEBHOOK_HOST"):
        CONFIG["host"] = host


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------
def resolve_params() -> dict:
    """
    从 header 解析参数。

    必传：channel, userId（userId 同时作为 target）
    可选：account（不传则从 channels.<channel>.account 取默认值）
    strict 模式额外校验 userId 是否在 channels.<channel>.users 中
    """
    def get_header(names):
        for name in names:
            val = request.headers.get(name, "").strip()
            if val:
                return val
        return None

    channel = get_header(["X-Channel", "channel"])
    user_id = get_header(["X-User-Id", "userId"])

    if not channel:
        abort(400, description="Missing required header: channel (or X-Channel)")
    if not user_id:
        abort(400, description="Missing required header: userId (or X-User-Id)")

    # 查 channel 配置
    channel_config = CHANNEL_MAP.get(channel)
    if not channel_config:
        abort(400, description=f"Unknown channel: {channel}")

    # strict 模式：校验 userId
    if MODE == "strict":
        allowed_users = channel_config.get("users", [])
        if allowed_users and user_id not in allowed_users:
            abort(403, description=f"userId not allowed for channel {channel}")

    # account：header 优先，否则取 config 默认
    account = get_header(["X-Account", "account"]) or channel_config.get("account", "default")
    target = user_id

    return {
        "channel": channel,
        "account": account,
        "target": target,
    }


# ---------------------------------------------------------------------------
# 发送消息
# ---------------------------------------------------------------------------
def send_to_openclaw(channel: str, account: str, target: str, message: str) -> bool:
    """调用 openclaw message send 发送消息。"""
    cmd = [
        "openclaw", "message", "send",
        "--channel", channel,
        "--account", account,
        "--target", target,
        "-m", message,
        "--json",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            log.info("Sent to %s via %s/%s", target, channel, account)
            return True
        else:
            log.error("openclaw message send failed: %s", result.stderr.strip())
            return False
    except subprocess.TimeoutExpired:
        log.error("openclaw message send timed out")
        return False
    except FileNotFoundError:
        log.error("openclaw CLI not found in PATH")
        return False


# ---------------------------------------------------------------------------
# 格式化消息
# ---------------------------------------------------------------------------
def format_message(data: dict, route: dict) -> str:
    """根据路由模板和请求体格式化最终消息。"""
    raw_message = data.get("message", "").strip()
    if not raw_message:
        abort(400, description="Empty message")

    template = route.get("template")
    if template:
        raw_message = template.replace("{{message}}", raw_message)
        for k, v in data.items():
            if k != "message":
                raw_message = raw_message.replace("{{" + k + "}}", str(v))

    level = data.get("level", route.get("defaultLevel", "info"))
    extra = data.get("extra")

    level_icons = {"info": "ℹ️", "warn": "⚠️", "error": "🔴"}
    icon = level_icons.get(level, "ℹ️")

    parts = [f"{icon} {raw_message}"]
    if extra and isinstance(extra, dict):
        for k, v in extra.items():
            parts.append(f"  {k}: {v}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 路由端点
# ---------------------------------------------------------------------------
@app.route("/webhook/<route_id>", methods=["POST"])
def webhook_dynamic(route_id: str):
    """
    通用 webhook 端点。

    必传 header:
        channel:  OpenClaw 渠道名
        userId:   目标用户 ID (同时作为 target)

    可选 header:
        account:  机器人账号 (不传则从 config channels 取默认值)

    请求体 (JSON):
        message:  消息内容 (必填)
        level:    通知级别 (可选)
        extra:    额外数据 (可选)
    """
    route = ROUTE_MAP.get(route_id)
    if not route:
        abort(404, description=f"Unknown route: {route_id}")

    params = resolve_params()
    data = request.get_json(silent=True) or {}
    final_message = format_message(data, route)

    ok = send_to_openclaw(
        channel=params["channel"],
        account=params["account"],
        target=params["target"],
        message=final_message,
    )

    if ok:
        return jsonify({"ok": True, "route": route_id, **params}), 200
    else:
        return jsonify({"ok": False, "error": "Failed to send via OpenClaw"}), 500


@app.route("/webhook/generic", methods=["POST"])
def webhook_generic():
    """通用直通端点（无路由模板）。"""
    params = resolve_params()
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        abort(400, description="Empty message")

    ok = send_to_openclaw(
        channel=params["channel"],
        account=params["account"],
        target=params["target"],
        message=message,
    )

    if ok:
        return jsonify({"ok": True, **params}), 200
    else:
        return jsonify({"ok": False}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "mode": MODE,
        "channels": list(CHANNEL_MAP.keys()),
        "routes": list(ROUTE_MAP.keys()),
    })


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="OpenClaw Webhook Channel")
    parser.add_argument("-c", "--config", help="配置文件路径")
    parser.add_argument("-p", "--port", type=int, help="监听端口")
    parser.add_argument("--host", help="监听地址")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    args = parser.parse_args()

    load_config(args.config)

    host = args.host or CONFIG.get("host", "0.0.0.0")
    port = args.port or CONFIG.get("port", 9876)
    debug = args.debug or CONFIG.get("debug", False)

    log.info("Starting OpenClaw Webhook Channel on %s:%d (mode=%s)", host, port, MODE)
    log.info("Channels: %s", list(CHANNEL_MAP.keys()))
    log.info("Routes: %s", list(ROUTE_MAP.keys()))

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
