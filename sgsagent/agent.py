"""Agent 顶层编排：把「武将描述」一键变成可落地的 FreeKill 扩展包。

generate() 返回结构化结果，同时（可选）把文件写到 outputs/<pkg_id>/ 下。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from . import codegen
from .config import settings
from .llm import LLMError, get_provider
from .normalizer import Normalizer
from .schemas import ModSpec


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def run_pipeline(description: str, provider: Optional[str] = None,
                 save: bool = True) -> Dict:
    """完整流水线：描述 -> 规范化 JSON -> FreeKill Lua 代码。

    返回：
      spec_json, files, warnings, stages, mod_dir, saved_paths ...
    任何阶段失败都会抛 LLMError/ValueError，由 Web 层转为友好错误。
    """
    started = time.time()
    stages = []

    # 1. 规范化
    prov = get_provider(provider)
    stages.append({
        "name": "描述规范化",
        "detail": f"调用 {prov.name()} 解析武将描述 -> 结构化 JSON",
        "ts": _now(),
    })
    normalizer = Normalizer(provider=prov)
    spec: ModSpec
    spec, warnings = normalizer.normalize(description)
    stages.append({
        "name": "结构化校验",
        "detail": f"解析成功：包 {spec.pkg_id}，武将 {len(spec.generals)} 名，"
                  f"技能 {sum(len(g.skills) for g in spec.generals)} 个",
        "ts": _now(),
    })

    # 2. 代码生成
    stages.append({
        "name": "FreeKill Lua 代码生成",
        "detail": f"依据 JSON 生成 init.lua + skills/*.lua（确定性骨架 + 模型 body）",
        "ts": _now(),
    })
    files, code_warnings = codegen.generate_mod(spec)
    warnings.extend(code_warnings)

    # 3. 落盘
    saved: List[str] = []
    mod_dir: Optional[str] = None
    if save:
        base = settings.output_dir / spec.pkg_id
        base.mkdir(parents=True, exist_ok=True)
        for f in files:
            p = _safe_path(base, f["path"], spec.pkg_id)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f["content"], encoding="utf-8")
            saved.append(str(p.relative_to(settings.output_dir)).replace("\\", "/"))
        mod_dir = str(base.resolve())
        stages.append({
            "name": "输出保存",
            "detail": f"已写入 {len(files)} 个文件到 outputs/{spec.pkg_id}/",
            "ts": _now(),
        })

    # 汇总可读摘要
    summary = spec.describe()
    summary += f"\n\n耗时 {time.time() - started:.1f}s；共生成 {len(files)} 个文件。"

    return {
        "ok": True,
        "provider": prov.id,
        "spec": spec.to_dict(),
        "spec_summary": summary,
        "files": files,
        "warnings": list(dict.fromkeys(warnings)),
        "stages": stages,
        "mod_dir": mod_dir,
        "saved_files": saved,
        "elapsed": round(time.time() - started, 2),
        "job_id": uuid.uuid4().hex[:8],
        "generated_at": _now(),
    }


def _safe_path(base: Path, rel: str, pkg_id: str) -> Path:
    """防止路径穿越：只允许产出在 outputs/<pkg_id>/ 之下的相对路径。"""
    parts = [p for p in rel.split("/") if p and p not in (".", "..", pkg_id)]
    return base.joinpath(*parts)


def run_cli(description: str, provider: Optional[str] = None,
            print_summary: bool = True) -> int:
    """命令行直接生成并落盘。成功返回 0。"""
    try:
        result = run_pipeline(description, provider=provider, save=True)
    except (LLMError, ValueError) as e:
        print(f"[错误] {e}")
        return 1
    if print_summary:
        print("=" * 50)
        print("规范化摘要：")
        print(result["spec_summary"])
        print("=" * 50)
        print("生成的代码文件：")
        for f in result["files"]:
            print(f"  - {f['path']}  ({len(f['content'])} 字符)")
        if result["warnings"]:
            print("\n提示（请人工复核）：")
            for w in result["warnings"]:
                print(f"  ! {w}")
        print(f"\n输出目录：{result['mod_dir']}")
    return 0
