-- 技能：圣火（shenghuo）｜类型：viewas
-- 由「三国杀 Agent」自动生成，请人工核对结算细节
local skill_shenghuo = fk.CreateSkill({ name = "shenghuo" })

skill_shenghuo:addEffect("viewas", {
  anim_type = "offensive",
  pattern = "slash",
  filter_pattern = { min_num = 1, max_num = 1, pattern = "." },
  view_as = function(self, player, cards)
  -- cards 为选中作为转换素材的牌（1 张）
  if #cards ~= 1 then return end
  local c = Fk:cloneCard("slash")
  c.skillName = "shenghuo"
  c:addSubcard(cards[1])
  return c
  end,
})

return skill_shenghuo
