"""Codegen：规范化 ModSpec -> FreeKill 扩展包 Lua 文件集合。

产出结构（与 FreeKill packages/<mod>/ 布局一致）：
  <pkg_id>/
    init.lua           包入口：注册包、扫描技能、注册武将、翻译文本
    skills/
      <skill_id>.lua   每个技能一个文件，fk.CreateSkill + addEffect(...)，return skill
    README_安装说明.txt

所有生成逻辑是确定性的：LLM 提供的只有 JSON（含各技能 body 的 Lua 片段），
这里负责包裹骨架、翻译表、校验与转义，避免模型直接生成易碎的整文件。
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .schemas import GeneralSpec, ModSpec, SkillSpec

# FreeKill 常用触发事件（new core 枚举常量名，不含 fk. 前缀）
KNOWN_EVENTS = {
    "Damaged", "DamageCaused", "DamageInflicted", "Damage", "Dying", "Death",
    "EventPhaseStart", "EventPhaseEnd", "EventPhaseChanging", "PlayerTurnStart",
    "PreHpChanged", "HpChanged", "PreCardUsed", "CardUsed", "PreTargetConfirmed",
    "TargetConfirmed", "CardResponded", "AskForPeaches", "PreJudge", "AskForRetrial",
    "EventAcquireSkill", "EventLoseSkill",
}

KINGDOM_LABEL = {
    "wei": "魏", "shu": "蜀", "wu": "吴", "qun": "群", "god": "神", "jin": "晋", "unknown": "未知",
}


def lua_escape(s) -> str:
    """把任意文本安全放进 Lua 双引号字符串。"""
    return (str(s).replace("\\", "\\\\").replace('"', '\\"')
            .replace("\r", "").replace("\n", "\\n").replace("\t", "\\t"))


def _indent(body: str, pad: str = "  ") -> str:
    lines = (body or "").split("\n")
    return "\n".join(pad + ln if ln.strip() else ln for ln in lines)


def check_lua_balance(code: str) -> List[str]:
    """朴素配平检查（忽略注释与字符串内容），返回告警。"""
    warns = []
    # 先剥离注释与字符串，再做统计
    stripped = re.sub(r"--[^\n]*", "", code)
    stripped = re.sub(r'"(?:\\.|[^"\\])*"', '""', stripped)
    stripped = re.sub(r"'[^']*'", "''", stripped)
    stripped = re.sub(r"\[\[.*?\]\]", "", stripped, flags=re.S)
    # Lua 需要 end 收尾的块关键字：function / if / for / while（repeat..until 例外）
    end_blocks = len(re.findall(r"\b(function|if|for|while)\b", stripped))
    ends = len(re.findall(r"\bend\b", stripped))
    if ends != end_blocks:
        warns.append(f"块结构疑似不配平：需 end 收尾的块 {end_blocks} 处，实际 end {ends} 处。")
    for left, right in (("(", ")"), ("{", "}"), ("[", "]")):
        if stripped.count(left) != stripped.count(right):
            warns.append(f"{left}{right} 数量不配平（{stripped.count(left)} vs {stripped.count(right)}）。")
    return warns


# ---------------------------------------------------------------- 技能文件
def generate_skill_file(skill: SkillSpec) -> Tuple[str, List[str]]:
    sid = skill.id
    lvar = f"skill_{sid}"
    warns: List[str] = []
    eff = skill.effect
    body = (eff.body or "").strip()
    if skill.is_compulsory:
        warns.append(f"技能 {skill.name or sid} 为锁定技：请人工确认是否设置 frequency = Skill.Compulsory。")

    lines = [
        f"-- 技能：{skill.name or sid}（{sid}）｜类型：{skill.type}",
        "-- 由「三国杀 Agent」自动生成，请人工核对结算细节",
        f"local {lvar} = fk.CreateSkill({{ name = \"{sid}\" }})",
        "",
    ]
    anim = lua_escape(eff.anim_type or "other")

    if skill.type == "trigger":
        event = eff.event or "Damaged"
        if event not in KNOWN_EVENTS:
            warns.append(f"触发事件 fk.{event} 不在常见白名单，请人工确认常量名。")
        lines += [
            f"{lvar}:addEffect(fk.{event}, {{",
            f'  anim_type = "{anim}",',
            "  on_use = function(self, event, target, player, data)",
            _indent(body),
            "  end,",
            "})",
        ]
    elif skill.type == "active":
        lines += [
            f'{lvar}:addEffect("active", {{',
            f'  anim_type = "{anim}",',
            f"  target_num = {eff.target_num},",
        ]
        if eff.min_card_num:
            lines.append(f"  min_card_num = {eff.min_card_num},")
        if eff.max_card_num:
            lines.append(f"  max_card_num = {eff.max_card_num},")
        if skill.description:
            lines.append(f'  prompt = "#{sid}-active",')
        lines += [
            "  on_use = function(self, room, effect)",
            _indent(body),
            "  end,",
            "})",
        ]
    elif skill.type == "viewas":
        pattern = lua_escape(eff.view_as_pattern or "slash")
        lines += [
            f'{lvar}:addEffect("viewas", {{',
            f'  anim_type = "{anim}",',
            f'  pattern = "{pattern}",',
            '  filter_pattern = { min_num = 1, max_num = 1, pattern = "." },',
            "  view_as = function(self, player, cards)",
            _indent(body),
            "  end,",
            "})",
        ]
    else:
        warns.append(f"技能 {skill.name or sid} 类型 {skill.type} 不受支持，跳过实现。")
        lines.append(f"-- 未支持类型：{skill.type}")

    lines += ["", f"return {lvar}", ""]
    content = "\n".join(lines)
    for w in check_lua_balance(content):
        warns.append(f"[{sid}] {w}")
    return content, warns


# ---------------------------------------------------------------- 包入口
def generate_init_file(spec: ModSpec, mod_folder: str) -> Tuple[str, List[str]]:
    warns: List[str] = []
    L = [
        "-- ============================================================",
        f"-- 三国杀 Agent 自动生成扩展：{spec.mod_name}（pkg: {spec.pkg_id}）",
        "-- 安装：将整个文件夹复制到 FreeKill 的 packages/ 目录下即可",
        "-- 结构：技能位于 skills/ 子目录，与官方 standard 包一致",
        "-- ============================================================",
        "",
        f'local extension = Package:new("{spec.pkg_id}")',
        f'extension.extensionName = "{lua_escape(mod_folder)}"',
        "",
        "-- 扫描并加载本包 skills/ 目录下的技能定义",
        'local prefix = "./packages/"',
        'if UsingNewCore then prefix = "./packages/freekill-core/" end',
        f'extension:loadSkillSkelsByPath(prefix .. "{mod_folder}/skills")',
        "",
        "-- ---------------- 武将注册 ----------------",
    ]
    for g in spec.generals:
        lines, w = _render_general(g)
        warns += w
        L.extend(lines)
        L.append("")

    L.append("-- ---------------- 翻译文本 ----------------")
    L.append("Fk:loadTranslationTable{")
    L.append(f'  ["{spec.pkg_id}"] = "{lua_escape(spec.mod_name)}",')
    L.append(f'  ["{spec.pkg_id}:name"] = "{lua_escape(spec.mod_name)}",')
    for g in spec.generals:
        L.append(f'  ["{g.id}"] = "{lua_escape(g.name)}",')
        if g.intro:
            L.append(f'  ["~{g.id}"] = "{lua_escape(g.intro)}",')
        for s in g.skills:
            L.append(f'  ["{s.id}"] = "{lua_escape(s.name)}",')
            L.append(f'  [":{s.id}"] = "{lua_escape(s.description)}",')
            if s.type == "active" and s.description:
                L.append(f'  ["#{s.id}-active"] = "{lua_escape(s.name)}：{lua_escape(s.description)}",')
    L.append("}")
    L.append("")
    L.append("return extension")
    content = "\n".join(L)
    for w in check_lua_balance(content):
        warns.append(w)
    return content, warns


def _render_general(g: GeneralSpec) -> Tuple[List[str], List[str]]:
    warns: List[str] = []
    # FreeKill General 位置参数：(ext, id, kingdom, max_hp, [hp, gender])
    args = [f'"{g.id}"', f'"{g.kingdom}"', str(g.max_hp)]
    need_hp = (g.hp is not None and g.hp != g.max_hp) or g.gender == "female"
    if need_hp:
        args.append(str(g.hp if g.hp is not None else g.max_hp))
        if g.gender == "female":
            args.append("General.Female")
    elif g.gender == "agender":
        # 无性别的特殊处理：先构造再覆写字段
        pass
    lines = [f"-- 武将：{g.name}（{g.id}） 势力 {g.kingdom} 体力 {g.max_hp}"]
    if g.intro:
        lines.append(f"-- 背景：{g.intro}")
    decl = f'local localGen = General(extension, {", ".join(args)})'
    if g.gender == "agender":
        decl += "\nlocalGen.gender = General.Agender"
    lines.append(decl)
    if g.hidden:
        lines.append("localGen.hidden = true")
    seen = set()
    for s in g.skills:
        if s.id in seen:
            warns.append(f"武将 {g.name or g.id} 的技能 id 重复：{s.id}")
        seen.add(s.id)
    skill_ids = ", ".join(f'"{s.id}"' for s in g.skills)
    lines.append(f"localGen:addSkills{{ {skill_ids} }}")
    lines.append("")
    return lines, warns


# ---------------------------------------------------------------- 整包
def generate_mod(spec: ModSpec) -> Tuple[List[Dict[str, str]], List[str]]:
    """生成整包文件列表：[{path, label, language, content}] + 去重警告。"""
    files: List[Dict[str, str]] = []
    warns: List[str] = []
    folder = spec.pkg_id

    content, w = generate_init_file(spec, folder)
    warns += w
    files.append({"path": f"{folder}/init.lua", "label": "init.lua", "language": "lua", "content": content})

    seen = set()
    for g in spec.generals:
        for s in g.skills:
            if s.id in seen:
                warns.append(f"技能 {s.id} 已重复出现，仅生成一份（FreeKill 要求技能全局唯一）。")
                continue
            seen.add(s.id)
            content, w = generate_skill_file(s)
            warns += w
            files.append({
                "path": f"{folder}/skills/{s.id}.lua",
                "label": f"skills/{s.id}.lua",
                "language": "lua",
                "content": content,
            })

    files.append({
        "path": f"{folder}/README_安装说明.txt",
        "label": "README_安装说明.txt",
        "language": "text",
        "content": _install_readme(spec),
    })

    uniq: List[str] = []
    seen_w: set = set()
    for w in warns:
        if w not in seen_w:
            seen_w.add(w)
            uniq.append(w)
    return files, uniq


def _install_readme(spec: ModSpec) -> str:
    lines = [
        "三国杀（FreeKill）武将扩展 · 安装与说明",
        "=" * 46,
        f"扩展名：{spec.mod_name}",
        f"包 ID：{spec.pkg_id}",
        f"生成说明：{spec.intro}",
        "",
        "【安装方法】",
        "  1. 把整个文件夹（含 init.lua 与 skills/ 子目录）放入 FreeKill 的",
        "     packages/ 目录下（与 standard/ 同级）；",
        "  2. 重新启动游戏，在选将界面即可找到本扩展武将。",
        "",
        "【结构】",
        "  init.lua         包入口（注册武将 / 技能 / 翻译）",
        "  skills/*.lua     每个技能一个文件，由引擎扫描加载",
        "",
        "【武将清单】",
    ]
    for i, g in enumerate(spec.generals, 1):
        lines.append(f"  {i}. {g.name}（{g.kingdom} / {g.gender} / {g.max_hp} 体力）")
        for s in g.skills:
            lines.append(f"     · {s.name}：{s.description}")
    lines += [
        "",
        "【注意】",
        "  · 代码由 AI 自动生成，仅供 DIY 参考。建议在游戏内实测每个技能，",
        "    核对触发时机、选牌范围与 FAQ 边界情况。",
        "  · 本生成器不生成 AI（addAI）与语音/立绘资源，缺少立绘会显示默认头像。",
    ]
    return "\n".join(lines)
