#!/usr/bin/env python3
"""
OpenClaw Webhook Channel — 通用 Webhook → OpenClaw 消息转发器

接收外部系统的 webhook 通知，根据请求头中的 userId 路由到对应的聊天联系人。
纯自动化转发，不经过 LLM 处理。

支持任意 webhook 来源：Auto_MAS、GitHub Actions、CI/CD、监控告警等。

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
USER_MAP: dict = {}
ROUTE_MAP: dict = {}


def load_config(path: str | None = None):
    """加载配置文件，合并环境变量覆盖。"""
    global CONFIG, USER_MAP, ROUTE_MAP

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

    USER_MAP = CONFIG.get("users", {})
    ROUTE_MAP = CONFIG.get("routes", {})

    # 环境变量覆盖
    if port := os.environ.get("OPENCLAW_WEBHOOK_PORT"):
        CONFIG["port"] = int(port)
    if host := os.environ.get("OPENCLAW_WEBHOOK_HOST"):
        CONFIG["host"] = host


# ---------------------------------------------------------------------------
# 核心: 发送消息到 OpenClaw
# ---------------------------------------------------------------------------
def send_to_openclaw(channel: str, account: str, target: str, message: str) -> bool:
    """调用 openclaw message send 发送消息（纯 CLI，不经过 LLM）。"""
    cmd = [
        "openclaw", "message", "send",
        "--channel", channel,
        "--account", account,
        "--target", target,
        "-m", message,
        "--json",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            log.info("Message sent to %s via %s/%s", target, channel, account)
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


def resolve_user(user_id: str) -> dict | None:
    """根据 userId 查找用户配置。"""
    return USER_MAP.get(user_id)


# ---------------------------------------------------------------------------
# 通用 Webhook 路由 (动态)
# ---------------------------------------------------------------------------
@app.route("/webhook/<route_id>", methods=["POST"])
def webhook_dynamic(route_id: str):
    """
    通用 webhook 端点，根据 route_id 查找路由配置。

    请求头:
        userId: 用户标识 (对应 config.json 中 users 的 key)

    请求体 (JSON):
        message:  消息内容 (必填)
        level:    通知级别 (可选: info/warn/error, 默认 info)
        extra:    额外数据 (可选, 任意 JSON)
    """
    # 查找路由配置
    route = ROUTE_MAP.get(route_id)
    if not route:
        log.warning("Unknown route: %s", route_id)
        abort(404, description=f"Unknown route: {route_id}")

    user_id = request.headers.get("userId", "").strip()
    if not user_id:
        # 尝试从路由配置获取默认 userId
        user_id = route.get("defaultUserId", "").strip()
    if not user_id:
        log.warning("Missing userId header")
        abort(400, description="Missing userId header")

    user_config = resolve_user(user_id)
    if not user_config:
        log.warning("Unknown userId: %s", user_id)
        abort(404, description=f"Unknown userId: {user_id}")

    data = request.get_json(silent=True) or {}
    raw_message = data.get("message", "").strip()
    if not raw_message:
        log.warning("Empty message from userId: %s", user_id)
        abort(400, description="Empty message")

    # 应用路由级别的消息模板
    template = route.get("template")
    if template:
        raw_message = template.replace("{{message}}", raw_message)
        for k, v in data.items():
            if k != "message":
                raw_message = raw_message.replace("{{" + k + "}}", str(v))

    # 构建最终消息
    level = data.get("level", route.get("defaultLevel", "info"))
    extra = data.get("extra")

    level_icons = {"info": "ℹ️", "warn": "⚠️", "error": "🔴"}
    icon = level_icons.get(level, "ℹ️")

    parts = [f"{icon} {raw_message}"]
    if extra and isinstance(extra, dict):
        for k, v in extra.items():
            parts.append(f"  {k}: {v}")

    final_message = "\n".join(parts)

    # 发送
    ok = send_to_openclaw(
        channel=user_config["channel"],
        account=user_config["account"],
        target=user_config["target"],
        message=final_message,
    )

    if ok:
        return jsonify({"ok": True, "userId": user_id, "route": route_id}), 200
    else:
        return jsonify({"ok": False, "error": "Failed to send via OpenClaw"}), 500


# ---------------------------------------------------------------------------
# 内置快捷路由
# ---------------------------------------------------------------------------
@app.route("/webhook/arknights", methods=["POST"])
def webhook_arknights():
    """明日方舟 Auto_MAS 快捷端点。"""
    return webhook_dynamic("arknights")


@app.route("/webhook/github", methods=["POST"])
def webhook_github():
    """GitHub webhook 快捷端点。"""
    return webhook_dynamic("github")


@app.route("/webhook/generic", methods=["POST"])
def webhook_generic():
    """通用 webhook 端点（无路由模板，直接转发 message）。"""
    user_id = request.headers.get("userId", "").strip()
    if not user_id:
        abort(400, description="Missing userId header")

    user_config = resolve_user(user_id)
    if not user_config:
        abort(404, description=f"Unknown userId: {user_id}")

    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        abort(400, description="Empty message")

    ok = send_to_openclaw(
        channel=user_config["channel"],
        account=user_config["account"],
        target=user_config["target"],
        message=message,
    )

    if ok:
        return jsonify({"ok": True}), 200
    else:
        return jsonify({"ok": False}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "users": list(USER_MAP.keys()),
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

    if not USER_MAP:
        log.error("No users configured! Edit config.json or set OPENCLAW_WEBHOOK_CONFIG")
        sys.exit(1)

    log.info("Starting OpenClaw Webhook Channel on %s:%d", host, port)
    log.info("Users: %s", list(USER_MAP.keys()))
    log.info("Routes: %s", list(ROUTE_MAP.keys()))

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
