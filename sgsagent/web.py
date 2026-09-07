"""本地 Web 服务（纯标准库 http.server，零第三方依赖）。

路由：
  GET  /                -> webui/index.html
  GET  /static/*        -> webui/ 下的静态资源（js/css）
  GET  /api/config      -> 可用 provider 与示例描述
  POST /api/generate    -> {description, provider?} 运行完整流水线
"""
from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from . import agent
from .config import PROJECT_ROOT, settings

WEBUI_DIR = PROJECT_ROOT / "webui"

PRESETS = [
    {
        "name": "触发技示例（受击摸牌）",
        "description": (
            "设计一个群势力4体力男性武将「铁壁卫士」。他的技能叫「铁壁」："
            "每当你受到1点伤害后，你可以摸一张牌。"
        ),
    },
    {
        "name": "主动技示例（弃牌摸牌）",
        "description": (
            "设计一个魏势力4体力女性武将「苏纵」，技能「纵横」："
            "出牌阶段限一次，你可以弃置任意张手牌，然后摸等量的牌。"
        ),
    },
    {
        "name": "转化技示例（红色当杀）",
        "description": (
            "设计一个蜀势力3体力女性武将「圣火圣女」，技能「圣火」："
            "你可以将一张红色手牌当【杀】使用或打出。"
        ),
    },
    {
        "name": "双技能武将（综合）",
        "description": (
            "设计吴势力4体力男武将「周瑜再世」：技能1「业炎」锁定技，当你造成火焰伤害后，"
            "你可以摸一张牌；技能2「英姿」出牌阶段限一次，你可以弃置一张牌，然后令一名其他角色"
            "选择弃置一张牌或受到你造成的1点伤害。"
        ),
    },
]


class Handler(BaseHTTPRequestHandler):
    server_version = "SanguoshaAgent/0.1"

    # ---------------- helpers ----------------
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 2 * 1024 * 1024:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt, *args):  # 精简日志
        print("[web] %s - %s" % (self.address_string(), fmt % args))

    # ---------------- routes ----------------
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
            self._serve_static(rel)
        elif path == "/api/config":
            self._json(200, {
                "ok": True,
                "providers": settings.provider_status(),
                "default_provider": settings.llm_provider,
                "presets": PRESETS,
            })
        else:
            self._json(404, {"ok": False, "error": "接口不存在"})

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/generate":
            self._api_generate()
        else:
            self._json(404, {"ok": False, "error": "接口不存在"})

    def _api_generate(self):
        body = self._read_body()
        description = (body.get("description") or "").strip()
        provider = body.get("provider") or None
        if not description:
            self._json(400, {"ok": False, "error": "请先输入武将描述。"})
            return
        if provider not in (None, "mock", "openai", "anthropic"):
            self._json(400, {"ok": False, "error": f"未知的模型提供方：{provider}"})
            return
        try:
            result = agent.run_pipeline(description, provider=provider, save=True)
            self._json(200, result)
        except Exception as e:  # noqa: BLE001
            self._json(500, {"ok": False, "error": f"生成失败：{e}"})

    # ---------------- static ----------------
    def _serve_static(self, rel: str) -> None:
        # 防目录穿越
        target = (WEBUI_DIR / rel).resolve()
        if not str(target).startswith(str(WEBUI_DIR.resolve())) or not target.is_file():
            self._json(404, {"ok": False, "error": "资源不存在"})
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/json", "application/javascript"):
            ctype += "; charset=utf-8"
        try:
            self._send(200, target.read_bytes(), ctype)
        except OSError:
            self._json(500, {"ok": False, "error": "读取资源失败"})


def create_server(host: str, port: int, provider: Optional[str] = None) -> ThreadingHTTPServer:
    if provider:
        import os
        os.environ["LLM_PROVIDER"] = provider
        # 重新加载配置（settings 为单例，直接覆写字段）
        settings.llm_provider = provider.strip().lower()
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str, port: int, provider: Optional[str] = None) -> None:
    srv = create_server(host, port, provider)
    url = f"http://{host}:{port}"
    print("=" * 56)
    print("  三国杀 Agent · 本地 Web 界面")
    print(f"  浏览器访问：{url}")
    print("  Ctrl+C 停止服务")
    print("=" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        srv.server_close()
