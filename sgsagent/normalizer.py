"""Normalizer：武将描述 -> 结构化 ModSpec。

流程：LLM 生成 JSON -> 健壮解析 -> ModSpec 容错构建 -> 兜底修复。
对于真实模型：解析失败可自修复重试（最多 2 轮）；仍失败则以尽力而为的方式产出可运行结构，
保证下游代码生成总是有东西可做，同时把警告传递给用户。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Tuple

from .llm import LLMClient, LLMError, get_provider
from .prompts import SYSTEM_TEMPLATE, build_normalize_user_prompt, build_repair_user_prompt
from .schemas import ModSpec


def extract_json(text: str) -> str:
    """从模型输出里抽取 JSON 主体（容忍代码块 / 前后缀文字）。"""
    text = (text or "").strip()
    # 去掉 ```json ... ``` 代码块
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fence:
        text = fence.group(1).strip()
    # 找不到花括号直接放弃
    if "{" not in text:
        raise ValueError("输出中未找到 JSON 对象（缺少 {）")
    start = text.index("{")
    end = text.rindex("}")
    return text[start:end + 1]


def parse_json(text: str) -> Dict:
    return json.loads(extract_json(text))


class Normalizer:
    """把口语化武将描述规范化为 ModSpec。"""

    def __init__(self, provider: Optional[LLMClient] = None, max_retries: int = 2):
        self.provider = provider or get_provider(None)
        self.max_retries = max_retries

    def normalize(self, description: str) -> Tuple[ModSpec, List[str]]:
        warnings: List[str] = []
        if not description or not description.strip():
            description = "群势力 4 体力男性武将「演示将」，技能「摸牌强化」：每当你的回合开始时，你可以摸一张牌。"
            warnings.append("描述为空，已使用演示描述。")

        raw = ""
        errors: List[str] = []
        try:
            raw = self.provider.complete(SYSTEM_TEMPLATE, build_normalize_user_prompt(description))
        except LLMError as e:
            # HTTP 等致命错误：不重试，走 Mock 保证演示可用，并明示
            warnings.append(f"大模型调用失败（{e}），已回退到 Mock 示例输出。")
            from .llm import MockProvider
            raw = MockProvider().complete(SYSTEM_TEMPLATE, build_normalize_user_prompt(description))

        spec: Optional[ModSpec] = None
        attempt = 0
        while attempt <= self.max_retries:
            try:
                data = parse_json(raw)
                spec, partial = ModSpec.from_dict(data), []
                break
            except Exception as e:  # noqa: BLE001
                errors.append(f"第 {attempt + 1} 次解析失败：{e}")
                if attempt < self.max_retries and not isinstance(self.provider, type(get_provider("mock"))):
                    try:
                        raw = self.provider.complete(
                            SYSTEM_TEMPLATE, build_repair_user_prompt(description, raw, str(e)))
                        attempt += 1
                        continue
                    except LLMError as e2:
                        errors.append(f"重试请求失败：{e2}")
                        break
                attempt += 1

        if spec is None:
            # 尽力而为：把已抽取的任何 JSON 拿去做容错构建（此时部分字段可能为默认值）
            try:
                data = parse_json(raw)
                spec = ModSpec.from_dict(data)
                warnings.append("结构化校验未完全通过，已按容错规则补全字段（请人工复核）。")
            except Exception as e:  # noqa: BLE001
                raise ValueError(
                    "描述规范化失败，无法产出合法结构。原因：\n" + "\n".join(errors + [str(e)])
                ) from e

        warnings.extend(self._post_fix(spec))
        return spec, warnings

    @staticmethod
    def _post_fix(spec: ModSpec) -> List[str]:
        """对缺失信息做确定性兜底，并返回附加警告。"""
        warns: List[str] = []
        if not spec.mod_name:
            spec.mod_name = "自定义武将包"
            warns.append("未提供扩展中文名，默认「自定义武将包」。")
        for g in spec.generals:
            if not g.name:
                g.name = g.id
                warns.append(f"武将 {g.id} 缺少中文名，已用 id 代替。")
            if not g.intro:
                g.intro = ""
            for s in g.skills:
                if not s.name:
                    s.name = s.id
                if not s.description:
                    s.description = f"{s.name}（自动生成的技能）"
                if not s.effect:
                    from .schemas import EffectSpec
                    s.effect = EffectSpec()
                # 触发技缺事件：给 Damaged 兜底
                if s.type == "trigger" and not s.effect.event:
                    s.effect.event = "Damaged"
                    warns.append(f"技能 {s.name}（{s.id}）未声明触发时机，默认在「受到伤害后 Damaged」触发。")
                # viewas 缺目标牌：给 slash 兜底
                if s.type == "viewas" and not s.effect.view_as_pattern:
                    s.effect.view_as_pattern = "slash"
                    warns.append(f"转化技 {s.name}（{s.id}）未声明视为的牌，默认视为【杀】(slash)。")
                # body 空：给占位
                body = (s.effect.body or "").strip()
                if not body:
                    s.effect.body = self._placeholder_body(s)
                    warns.append(f"技能 {s.name}（{s.id}）缺少 Lua 实现体，已生成 TODO 占位代码，请人工补全。")
        if not spec.generals:
            warns.append("规范化结果中没有任何武将，请检查描述。")
        return warns

    @staticmethod
    def _placeholder_body(skill) -> str:
        if skill.type == "trigger":
            return (
                "-- TODO: 在此实现「{name}」的触发效果（可用 API 见系统提示素材库）\n"
                "local room = player.room\n"
                '-- 例：room:damage{{ from = player, to = data.from, damage = 1, skillName = "{sid}" }}\n'
                "return false\n"
            ).format(name=skill.name, sid=skill.id)
        if skill.type == "active":
            return (
                "-- TODO: 在此实现主动技「{name}」效果（可用 effect.from / effect.cards / room）\n"
                'local room = effect.from.room\n'
                '-- 例：room:throwCard(effect.cards, "{sid}", effect.from, effect.from)\n'
            ).format(name=skill.name, sid=skill.id)
        # viewas
        return (
            "-- TODO: 在此实现转化技「{name}」，把 cards 转成虚拟牌后 return\n"
            'if #cards < 1 then return end\n'
            'local c = Fk:cloneCard("{pattern}")\n'
            'c.skillName = "{sid}"\n'
            "c:addSubcard(cards[1])\n"
            "return c\n"
        ).format(name=skill.name, sid=skill.id, pattern=skill.effect.view_as_pattern or "slash")
