"""命令行单发模式：描述 -> 规范化 JSON + Lua 代码 落盘。

用法：
  python -m sgsagent.cli --provider mock "武将描述……"
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .agent import run_pipeline  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="三国杀 Agent 单发命令行")
    ap.add_argument("description", help="武将描述文本")
    ap.add_argument("--provider", default=None, choices=["mock", "openai", "anthropic"],
                    help="模型提供方（默认读 .env）")
    ap.add_argument("--json", action="store_true", help="额外输出完整规范化 JSON")
    args = ap.parse_args()

    try:
        result = run_pipeline(args.description, provider=args.provider, save=True)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] {e}", file=sys.stderr)
        return 1

    print("=" * 52)
    print("规范化摘要：")
    print(result["spec_summary"])
    print("=" * 52)
    print("生成文件：")
    for f in result["files"]:
        print(f"  - {f['path']}  ({len(f['content'])} chars)")
    if result["warnings"]:
        print("\n请人工复核：")
        for w in result["warnings"]:
            print(f"  ! {w}")
    if args.json:
        print("\n规范化 JSON：")
        print(json.dumps(result["spec"], ensure_ascii=False, indent=2))
    print(f"\n输出目录：{result['mod_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
