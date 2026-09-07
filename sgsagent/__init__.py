"""三国杀 Agent —— 武将描述自动规范化 + FreeKill Lua 代码生成。

模块构成:
  config.py     环境变量与模型配置
  schemas.py    武将规范化 JSON 的数据模型（引擎中立）与容错解析
  llm.py        大模型客户端抽象（mock / openai / anthropic）
  prompts.py    规范化阶段的提示词（含 FreeKill 代码素材库）
  normalizer.py 描述 -> 结构化 JSON 的规范化器（含自修复）
  codegen.py    结构化 JSON -> FreeKill Lua 代码生成器
  agent.py      顶层编排
  web.py        本地 Web 服务（标准库 HTTP）
"""
__version__ = "0.1.0"
