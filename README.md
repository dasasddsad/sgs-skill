# 三国杀 Agent（FreeKill）

把一句口语化的**武将描述**自动变成：
1. 一份**规范化结构化 JSON**（武将 id / 势力 / 性别 / 体力 / 技能拆解 / 规范描述 / 实现思路）；
2. 一个**可直接放入 FreeKill 加载的 Lua 扩展包**（`init.lua` + `skills/*.lua`）。

> 目标引擎：FreeKill（新月杀，`Qsgs-Fans/FreeKill` 新版核心）。
> 代码骨架取自官方 `packages/standard` 标准包的真实写法（`Package:new` / `General(...)` /
> `fk.CreateSkill` / `skill:addEffect(fk.Damaged | "active" | "viewas")` / `Fk:loadTranslationTable`）。

## 快速开始（零依赖）

```bash
# 1. 启动 Web 服务（默认使用内置 Mock 模型，离线可跑）
python run_server.py

# 2. 浏览器打开 http://127.0.0.1:8000 ，输入描述 → 生成
```

也可命令行直接生成到 `outputs/`：

```bash
python -m sgsagent.cli --provider mock "设计一个群势力4体力男性武将铁壁卫士，技能铁壁：每当你受到1点伤害后，你可以摸一张牌。"
```

## 接真实大模型

复制 `.env.example` 为 `.env`，任选其一填写：

| 提供方 | 配置 | 说明 |
|---|---|---|
| mock | — | 内置离线示例，永远可用 |
| openai | `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `OPENAI_MODEL` | 智谱 GLM / DeepSeek / OpenAI 等任意兼容端点 |
| anthropic | `ANTHROPIC_API_KEY`（可配 `ANTHROPIC_MODEL`） | Claude |

`LLM_PROVIDER=mock|openai|anthropic` 决定默认提供方；Web 界面里也可以临时切换。
未配置密钥而选择真实提供方时会返回明确错误（不会静默降级），便于排查。

## 架构

```
run_server.py               本地 Web 服务入口（纯标准库 http.server）
webui/                      前端页面（无任何外部 CDN，可完全离线）
sgsagent/
  schemas.py                规范化 JSON 数据模型 + 中文别名/ID 清洗/容错解析
  llm.py                    模型抽象层：mock / OpenAI 兼容 / Anthropic（urllib 实现，无需 SDK）
  prompts.py                规范化提示词（内置 FreeKill API 素材库，取自官方 standard 包）
  normalizer.py             描述 → ModSpec（含解析失败自修复重试与确定性兜底）
  codegen.py                ModSpec → FreeKill Lua 文件（骨架确定生成，仅函数体来自模型）
  agent.py                  顶层编排（流水线日志 / 落盘 / CLI）
  web.py                    HTTP 路由
outputs/<pkg_id>/           生成的扩展包
```

## 输出目录结构（对齐 FreeKill packages 约定）

```
outputs/<pkg_id>/
  init.lua                  包入口：Package:new + 扫描 skills/ + General 注册 + 翻译表
  skills/<skill_id>.lua     每个技能一个文件
  README_安装说明.txt        安装方法 + 武将清单
```

把 `<pkg_id>` 整个文件夹复制进 FreeKill 的 `packages/` 目录，重启游戏即可选将测试。

## 已知边界

- 技能触发逻辑以 **body** 字段形式由模型编写，代码生成器只负责包裹骨架、转义与括号配平检查，
  因此语义正确性依赖所选模型质量，请在游戏内实测。
- 不生成 AI（`addAI`）、语音与立绘资源；立绘缺失时显示默认头像。
- “锁定技 / 强制发动”等仅以注释提示，未写入引擎级 `frequency` 属性。

## 后续可扩展点

- 接入你已有的 RAG / Milvus 武将库，在规范化前做“同设计武将查重”；
- 按描述难度自动降级模型（如简单描述用 flash 级、复杂双技能用更强模型）；
- 用 `luac -p` 或 luacheck 对生成代码做静态校验并回灌给模型自修复。
