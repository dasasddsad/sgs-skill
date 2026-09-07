"""武将「规范化」结构化 JSON 的数据模型（引擎中立，FreeKill 友好）。

设计原则：
- 所有字段均为确定性解析（对 LLM 输出尽量宽容，缺省值合理兜底）；
- id 全部清洗为合法 Lua 标识符；
- 势力/性别支持中文别名映射。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------- 常量与映射 ----------------

KINGDOM_ALIAS = {
    "wei": "wei", "魏": "wei", "魏国": "wei",
    "shu": "shu", "蜀": "shu", "蜀国": "shu",
    "wu": "wu", "吴": "wu", "吴国": "wu",
    "qun": "qun", "群": "qun", "群雄": "qun",
    "god": "god", "神": "god",
    "jin": "jin", "晋": "jin", "晋国": "jin",
    "unknown": "unknown", "未知": "unknown",
}
GENDER_ALIAS = {
    "male": "male", "男": "male", "男性": "male", "m": "male",
    "female": "female", "女": "female", "女性": "female", "f": "female",
    "agender": "agender", "无性": "agender", "a": "agender",
}
SKILL_TYPES = ("trigger", "active", "viewas", "other")


def clean_id(raw: Any, fallback: str = "gen") -> str:
    """把任意文本清洗成合法小写标识符（a-z0-9_，首字符为字母或下划线）。"""
    s = str(raw or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = fallback
    if not (s[0].isalpha() or s[0] == "_"):
        s = "_" + s
    if len(s) > 48:
        s = s[:48].rstrip("_")
    return s


def _pick(obj: Dict[str, Any], keys, default=None):
    for k in keys:
        if isinstance(obj, dict) and k in obj and obj[k] not in (None, ""):
            return obj[k]
    return default


# ---------------- 数据模型 ----------------

@dataclass
class EffectSpec:
    """一个技能效果。对触发技而言，type=trigger；对主动技 type=active；对转化技 type=viewas。"""
    type: str = "trigger"
    # trigger：触发时机常量名（不含 fk. 前缀），如 Damaged
    event: Optional[str] = None
    frequency: str = "normal"          # normal / compulsory（锁定技）
    # active：目标数 / 是否选牌 / 选牌数量
    target_num: int = 0
    min_card_num: int = 0
    max_card_num: int = 0
    anim_type: str = "other"
    # viewas：视为使用的目标牌名，如 slash
    view_as_pattern: Optional[str] = None
    # Lua 函数体（不含 function 声明行，代码生成时自动包裹）
    body: str = ""
    comment: str = ""

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "EffectSpec":
        obj = obj or {}
        typ = _pick(obj, ("type", "effect_type", "kind", "类别", "类型"), "") or ""
        typ = str(typ).lower()
        if typ not in SKILL_TYPES:
            # 自动推断
            if _pick(obj, ("view_as", "view_as_pattern", "pattern"), None):
                typ = "viewas"
            elif _pick(obj, ("event", "trigger_event", "触发时机"), None):
                typ = "trigger"
            elif _pick(obj, ("card_filter", "target_num"), None) is not None or any(
                    k in obj for k in ("出牌阶段",)):
                typ = "active"
            else:
                typ = "trigger"
        freq = _pick(obj, ("frequency", "compulsory", "锁定技"), "normal")
        if isinstance(freq, bool):
            freq = "compulsory" if freq else "normal"
        if str(freq).lower() in ("锁定", "锁定技", "compulsory", "true", "是", "强制"):
            freq = "compulsory"
        else:
            freq = "normal"
        event = _pick(obj, ("event", "trigger_event", "触发时机"), None)
        if event is not None:
            event = str(event).strip().lstrip("fk.").lstrip(".")
            if not event or event == "none":
                event = None
        return cls(
            type=typ,
            event=event,
            frequency=freq,
            target_num=_to_int(_pick(obj, ("target_num", "目标数"), 0), 0),
            min_card_num=_to_int(_pick(obj, ("min_card_num", "min_num", "最少选牌", "least"), 0), 0),
            max_card_num=_to_int(_pick(obj, ("max_card_num", "max_num", "最多选牌", "most"), 0), 0),
            anim_type=str(_pick(obj, ("anim_type", "动画"), "other") or "other"),
            view_as_pattern=_pick(obj, ("view_as_pattern", "pattern", "视为牌"), None),
            body=str(_pick(obj, ("body", "lua", "lua_body", "code", "on_use_body", "view_as", "函数体", "代码"), "") or ""),
            comment=str(_pick(obj, ("comment", "note", "设计说明"), "") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "event": self.event,
            "frequency": self.frequency,
            "target_num": self.target_num,
            "min_card_num": self.min_card_num,
            "max_card_num": self.max_card_num,
            "anim_type": self.anim_type,
            "view_as_pattern": self.view_as_pattern,
            "body": self.body,
            "comment": self.comment,
        }


@dataclass
class SkillSpec:
    id: str
    name: str = ""
    description: str = ""
    effect: Optional[EffectSpec] = None
    prompt_text: str = ""       # 展示在游戏界面的说明（无则用 description）

    @property
    def type(self) -> str:
        return (self.effect.type if self.effect else "trigger")

    @property
    def is_compulsory(self) -> bool:
        return bool(self.effect and self.effect.frequency == "compulsory")

    @classmethod
    def from_dict(cls, obj: Dict[str, Any], idx: int = 0) -> "SkillSpec":
        obj = obj or {}
        raw_id = _pick(obj, ("id", "skill_id", "name_en", "英文名"), f"skill_{idx}")
        # 允许直接给出多个 effect（罕见），取第一个最完整者
        eff_obj = _pick(obj, ("effect", "effects", "effect_spec", "效果"), None)
        if isinstance(eff_obj, list):
            eff_obj = eff_obj[0] if eff_obj else {}
        if isinstance(eff_obj, dict):
            if "name" in eff_obj and "id" not in eff_obj:
                eff_obj["id"] = eff_obj["name"]
        else:
            eff_obj = {}
        eff_obj.setdefault("body", obj.get("body") or obj.get("lua") or obj.get("code"))
        eff_obj.setdefault("type", obj.get("type"))
        eff_obj.setdefault("event", obj.get("event") or obj.get("trigger_event"))
        eff_obj.setdefault("view_as_pattern", obj.get("view_as_pattern") or obj.get("pattern"))
        eff_obj.setdefault("compulsory", obj.get("compulsory"))
        eff_obj.setdefault("target_num", obj.get("target_num"))
        eff_obj.setdefault("min_card_num", obj.get("min_card_num"))
        eff_obj.setdefault("max_card_num", obj.get("max_card_num"))
        eff_obj.setdefault("anim_type", obj.get("anim_type"))
        eff_obj.setdefault("comment", obj.get("comment") or obj.get("note"))
        return cls(
            id=clean_id(raw_id, f"skill_{idx}"),
            name=str(_pick(obj, ("name", "技能名"), "") or ""),
            description=str(_pick(obj, ("description", "desc", "text", "技能描述", "描述"), "") or ""),
            effect=EffectSpec.from_dict(eff_obj),
            prompt_text=str(_pick(obj, ("prompt", "prompt_text", "发动提示"), "") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "prompt_text": self.prompt_text,
            "effect": (self.effect.to_dict() if self.effect else None),
        }


@dataclass
class GeneralSpec:
    id: str
    name: str = ""
    kingdom: str = "qun"
    max_hp: int = 4
    hp: Optional[int] = None
    gender: str = "male"
    hidden: bool = False
    intro: str = ""
    skills: List[SkillSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, obj: Dict[str, Any], idx: int = 0) -> "GeneralSpec":
        obj = obj or {}
        raw_id = _pick(obj, ("id", "general_id", "name_en", "武将名id"), f"general_{idx}")
        kingdom = str(_pick(obj, ("kingdom", "阵营", "势力", "country"), "qun") or "qun")
        kingdom = KINGDOM_ALIAS.get(str(kingdom).lower().strip(), kingdom)
        if kingdom not in ("wei", "shu", "wu", "qun", "god", "jin", "unknown"):
            kingdom = "qun"
        gender = str(_pick(obj, ("gender", "sex", "性别"), "male") or "male")
        gender = GENDER_ALIAS.get(str(gender).lower().strip(), "male")
        hp_raw = _pick(obj, ("hp", "current_hp", "当前体力"), None)
        skills_raw = _pick(obj, ("skills", "skill", "技能"), []) or []
        if isinstance(skills_raw, dict):
            skills_raw = [skills_raw]
        skills = [SkillSpec.from_dict(s, i) for i, s in enumerate(skills_raw) if isinstance(s, dict)]
        return cls(
            id=clean_id(raw_id, f"general_{idx}"),
            name=str(_pick(obj, ("name", "武将名", "display_name"), "") or ""),
            kingdom=kingdom,
            max_hp=_clamp_hp(_to_int(_pick(obj, ("max_hp", "hp_max", "体力上限", "体力"), 4), 4), 4),
            hp=_clamp_hp(_to_int(hp_raw, None), None),
            gender=gender,
            hidden=bool(_pick(obj, ("hidden", "隐藏"), False)),
            intro=str(_pick(obj, ("intro", "背景", "简介", "story"), "") or ""),
            skills=skills,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kingdom": self.kingdom,
            "max_hp": self.max_hp,
            "hp": self.hp if self.hp is not None else self.max_hp,
            "gender": self.gender,
            "hidden": self.hidden,
            "intro": self.intro,
            "skills": [s.to_dict() for s in self.skills],
        }


@dataclass
class ModSpec:
    """一次「武将描述规范化」的完整产出。"""
    pkg_id: str
    mod_name: str = ""
    intro: str = ""
    generals: List[GeneralSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> "ModSpec":
        obj = obj or {}
        pkg_id = clean_id(_pick(obj, ("pkg_id", "package_id", "pack_id", "mod_id"), "my_mod"), "my_mod")
        gens = _pick(obj, ("generals", "generals_list", "武将", "heroes"), []) or []
        if isinstance(gens, dict):  # 只有一个武将时可能是对象
            gens = [gens]
        return cls(
            pkg_id=pkg_id,
            mod_name=str(_pick(obj, ("mod_name", "package_name", "name", "扩展名", "标题"), "") or ""),
            intro=str(_pick(obj, ("intro", "mod_intro", "简介", "说明"), "") or ""),
            generals=[GeneralSpec.from_dict(g, i) for i, g in enumerate(gens) if isinstance(g, dict)],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pkg_id": self.pkg_id,
            "mod_name": self.mod_name,
            "intro": self.intro,
            "generals": [g.to_dict() for g in self.generals],
        }

    def describe(self) -> str:
        """人类可读的规范化摘要（用于前端预览）。"""
        lines = [f"包ID：{self.pkg_id}（{self.mod_name or '-'}）"]
        for i, g in enumerate(self.generals, 1):
            skills = "、".join(f"{s.name or s.id}" for s in g.skills) or "（无技能）"
            lines.append(
                f"{i}. {g.name or g.id}｜{g.kingdom} 势力｜{g.gender}｜"
                f"{g.max_hp}体力｜技能：{skills}"
            )
            for s in g.skills:
                st = {"trigger": "触发", "active": "主动", "viewas": "转化", "other": "其他"}.get(s.type, s.type)
                ev = f" @{s.effect.event}" if (s.type == "trigger" and s.effect and s.effect.event) else ""
                lines.append(f"   - [{st}{ev}] {s.name or s.id}：{s.description or s.id}")
        return "\n".join(lines)


# ---------------- 工具函数 ----------------

def _to_int(v: Any, default):
    if v in (None, ""):
        return default
    try:
        return int(str(v))
    except (TypeError, ValueError):
        try:
            return int(float(str(v)))
        except (TypeError, ValueError):
            return default


def _clamp_hp(v, default):
    if v is None:
        return default
    return max(1, min(99, v))
