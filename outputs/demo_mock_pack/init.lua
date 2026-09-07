-- ============================================================
-- 三国杀 Agent 自动生成扩展：Mock 示例扩展（pkg: demo_mock_pack）
-- 安装：将整个文件夹复制到 FreeKill 的 packages/ 目录下即可
-- 结构：技能位于 skills/ 子目录，与官方 standard 包一致
-- ============================================================

local extension = Package:new("demo_mock_pack")
extension.extensionName = "demo_mock_pack"

-- 扫描并加载本包 skills/ 目录下的技能定义
local prefix = "./packages/"
if UsingNewCore then prefix = "./packages/freekill-core/" end
extension:loadSkillSkelsByPath(prefix .. "demo_mock_pack/skills")

-- ---------------- 武将注册 ----------------
-- 武将：圣火圣女（mock_v） 势力 shu 体力 3
-- 背景：（Mock 示例）演示 viewas 型技能：圣火。
local localGen = General(extension, "mock_v", "shu", 3, 3, General.Female)
localGen:addSkills{ "shenghuo" }


-- ---------------- 翻译文本 ----------------
Fk:loadTranslationTable{
  ["demo_mock_pack"] = "Mock 示例扩展",
  ["demo_mock_pack:name"] = "Mock 示例扩展",
  ["mock_v"] = "圣火圣女",
  ["~mock_v"] = "（Mock 示例）演示 viewas 型技能：圣火。",
  ["shenghuo"] = "圣火",
  [":shenghuo"] = "你可以将一张红色手牌当【杀】使用或打出。",
}

return extension