#!/usr/bin/env python3
"""三国杀 Agent - 本地 Web 服务入口。

用法：
  python run_server.py                     # 用 .env / 环境变量配置（默认 mock）
  python run_server.py --provider openai   # 指定模型提供方 mock|openai|anthropic
  python run_server.py --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import argparse
import os
import sys

# 让 Python 能找到 sgsagent 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser(description="三国杀 Agent Web 服务")
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--provider", default=None, choices=["mock", "openai", "anthropic", "auto"],
                    help="模型提供方（默认读取 .env 的 LLM_PROVIDER）")
    args = ap.parse_args()

    # 命令行优先：直接把 provider 写入环境，再导入配置
    if args.provider and args.provider != "auto":
        os.environ["LLM_PROVIDER"] = args.provider

    from sgsagent.web import serve
    serve(args.host, args.port, provider=(None if args.provider == "auto" else args.provider))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
