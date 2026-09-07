"""环境变量与运行配置（标准库解析 .env，无需 python-dotenv）。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        self.llm_provider = os.environ.get("LLM_PROVIDER", "mock").strip().lower()
        self.openai_base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.openai_model = os.environ.get("OPENAI_MODEL", "").strip()
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5").strip()
        self.host = os.environ.get("HOST", "127.0.0.1").strip()
        try:
            self.port = int(os.environ.get("PORT", "8000"))
        except ValueError:
            self.port = 8000
        self.output_dir = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "outputs"))

    def provider_available(self, provider: str) -> bool:
        provider = (provider or "").lower()
        if provider == "mock":
            return True
        if provider == "openai":
            return bool(self.openai_base_url and self.openai_api_key)
        if provider == "anthropic":
            return bool(self.anthropic_api_key)
        return False

    def provider_status(self) -> dict:
        return [
            {"id": "mock", "name": "Mock（本地示例，无需联网）", "configured": True},
            {"id": "openai", "name": "OpenAI 兼容接口（智谱/DeepSeek…）", "configured": self.provider_available("openai")},
            {"id": "anthropic", "name": "Anthropic Claude", "configured": self.provider_available("anthropic")},
        ]


settings = Settings()
