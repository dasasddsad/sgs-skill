"""大模型客户端抽象层。

设计为可配置 / 可 mock：
  - MockProvider    内置离线演示，不依赖任何网络与密钥；
  - OpenAICompat    任意 OpenAI 兼容 ChatCompletions 端点（智谱 GLM / DeepSeek / OpenAI…）
                     优先使用 urllib 直接发 HTTP 请求（无需安装 SDK）；
  - AnthropicProvider  Claude Messages API。

通过工厂函数 get_provider(provider_id) 创建实例；provider 传 None 时按环境变量 LLM_PROVIDER
自动选择，未配置可用密钥时回退到 mock。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Optional

from .config import settings

# 厂商 model 默认值（用于 URL 配置后偷懒不填 model）
_DEFAULT_MODELS = {"zhipu": "glm-4-flash", "deepseek": "deepseek-chat", "moonshot": "moonshot-v1-8k"}


class LLMError(RuntimeError):
    pass


class LLMClient(ABC):
    """最小接口：一次系统提示 + 一次用户提示，返回文本。"""
    id: str = "base"

    @abstractmethod
    def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        raise NotImplementedError

    def name(self) -> str:
        return self.id


class MockProvider(LLMClient):
    """离线 Mock：根据提示词中的阶段标记与描述关键词返回预置结果。"""
    id = "mock"

    def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        return build_mock_normalized_json(user)


class _HttpBase(LLMClient):
    """基于 urllib 的 HTTP JSON 基类。"""

    def _post_json(self, url: str, headers: dict, payload: dict, timeout: int = 120) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:  # 读取错误体以便给出可诊断信息
            raw = e.read().decode("utf-8", "replace")
            raise LLMError(f"HTTP {e.code}：{raw[:500]}") from e
        except urllib.error.URLError as e:
            raise LLMError(f"无法连接模型服务：{e}") from e
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMError(f"模型返回非 JSON：{raw[:300]}") from e


class OpenAICompatProvider(_HttpBase):
    """OpenAI 兼容 Chat Completions。base_url 支持智谱 / DeepSeek 等。"""
    id = "openai"

    def __init__(self, base_url: str, api_key: str, model: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model or _default_model(base_url)

    def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        if not self.api_key:
            raise LLMError("未配置 OPENAI_API_KEY")
        url = self.base_url + "/chat/completions"
        if not self.base_url.endswith("/chat/completions") and "/chat/completions" not in self.base_url:
            url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        data = self._post_json(
            url,
            {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            payload,
        )
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"响应结构异常：{str(data)[:300]}") from e


class AnthropicProvider(_HttpBase):
    """Anthropic Claude Messages API（无需安装 anthropic SDK）。"""
    id = "anthropic"

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or "claude-sonnet-4-5"

    def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        if not self.api_key:
            raise LLMError("未配置 ANTHROPIC_API_KEY")
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": self.model,
            "max_tokens": 6000,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = self._post_json(
            url,
            {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            payload,
        )
        try:
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"响应结构异常：{str(data)[:300]}") from e


def _default_model(base_url: str) -> str:
    for key, model in _DEFAULT_MODELS.items():
        if key in (base_url or "").lower():
            return model
    return "glm-4-flash"


def get_provider(provider: Optional[str] = None) -> LLMClient:
    """按指定 id（mock/openai/anthropic）创建客户端；缺省时按环境自动选择，可用性不足回退 mock。"""
    pid = (provider or settings.llm_provider or "mock").lower()
    if pid == "openai" and settings.provider_available("openai"):
        return OpenAICompatProvider(settings.openai_base_url, settings.openai_api_key, settings.openai_model)
    if pid == "anthropic" and settings.provider_available("anthropic"):
        return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
    if pid in ("mock", "openai", "anthropic"):
        # 用户显式点名但缺密钥 -> 给出清晰错误，绝不静默换 mock
        if pid == "openai":
            raise LLMError("所选提供方 openai 未配置：请设置 OPENAI_BASE_URL 与 OPENAI_API_KEY")
        if pid == "anthropic":
            raise LLMError("所选提供方 anthropic 未配置：请设置 ANTHROPIC_API_KEY")
    # mock 或无有效配置
    return MockProvider()


# ---------------- Mock 数据：规范化后的预置产出 ----------------

def _mock_skill(typ: str) -> dict:
    base = {
        "trigger": {
            "id": "tiebi",
            "name": "铁壁",
            "description": "当你受到 1 点伤害后，你可以摸一张牌。",
            "type": "trigger",
            "event": "Damaged",
            "anim_type": "masochism",
            "comment": "典型防御触发技：受击后获得资源。",
            "body": (
                "-- 受击结算：伤害来源判定 + 摸牌\n"
                "local room = player.room\n"
                "local from = data.from\n"
                "if from and not from.dead then\n"
                "  room:doIndicate(player.id, { from.id })\n"
                "end\n"
                "room:notifySkillInvoked(player, \"tiebi\", \"masochism\")\n"
                "player:drawCards(1, \"tiebi\")\n"
            ),
        },
        "active": {
            "id": "zongheng",
            "name": "纵横",
            "description": "出牌阶段限一次，你可以弃置任意张手牌，然后摸等量的牌。",
            "type": "active",
            "target_num": 0,
            "min_card_num": 1,
            "max_card_num": 0,   # 0 表示不限制
            "anim_type": "drawcard",
            "comment": "典型主动技（类制衡）。",
            "body": (
                "-- effect.from 为使用者，effect.cards 为所选牌\n"
                "local room = effect.from.room\n"
                "room:throwCard(effect.cards, \"zongheng\", effect.from, effect.from)\n"
                "effect.from:drawCards(#effect.cards, \"zongheng\")\n"
            ),
        },
        "viewas": {
            "id": "shenghuo",
            "name": "圣火",
            "description": "你可以将一张红色手牌当【杀】使用或打出。",
            "type": "viewas",
            "view_as_pattern": "slash",
            "filter_min": 1,
            "filter_max": 1,
            "filter_pattern": ".|.|red",
            "anim_type": "offensive",
            "comment": "典型转化技（类武圣）。",
            "body": (
                "-- cards 为选中作为转换素材的牌（1 张）\n"
                "if #cards ~= 1 then return end\n"
                "local c = Fk:cloneCard(\"slash\")\n"
                "c.skillName = \"shenghuo\"\n"
                "c:addSubcard(cards[1])\n"
                "return c\n"
            ),
        },
    }
    return base[typ]


def _mock_general(typ: str, kingdom: str = "qun", hp: int = 4, gender: str = "male") -> dict:
    skill = _mock_skill(typ)
    if typ == "trigger":
        name, gender, kingdom, hp = "铁壁卫士", "male", "qun", 4
    elif typ == "active":
        name, gender, kingdom, hp = "纵横家·苏纵", "male", "wei", 4
    else:
        name, gender, kingdom, hp = "圣火圣女", "female", "shu", 3
    return {
        "id": "mock_" + name.split("·")[0].split("·")[0][:6] + str(typ)[0],
        "name": name,
        "kingdom": kingdom,
        "max_hp": hp,
        "hp": hp,
        "gender": gender,
        "intro": f"（Mock 示例）演示 {typ} 型技能：{skill['name']}。",
        "skills": [skill],
    }


def build_mock_normalized_json(user_text: str) -> str:
    """根据用户描述中的关键词，返回对应类型技能 Mock 规范化 JSON（纯文本）。"""
    u = (user_text or "").lower()
    typ = "trigger"
    if "出牌阶段" in u or "弃置" in u or "限一次" in u:
        typ = "active"
    elif ("当【杀】" in u) or ("视为" in u and "杀" in u) or ("红色牌" in u):
        typ = "viewas"
    gen = _mock_general(typ)
    import json as _json
    spec = {
        "pkg_id": "demo_mock_pack",
        "mod_name": "Mock 示例扩展",
        "intro": "由 Mock 客户端离线生成的演示武将，覆盖 %s 型技能。" % typ,
        "generals": [gen],
    }
    return _json.dumps(spec, ensure_ascii=False, indent=2)
