-- 技能：纵横（zongheng）｜类型：active
-- 由「三国杀 Agent」自动生成，请人工核对结算细节
local skill_zongheng = fk.CreateSkill({ name = "zongheng" })

skill_zongheng:addEffect("active", {
  anim_type = "drawcard",
  target_num = 0,
  min_card_num = 1,
  prompt = "#zongheng-active",
  on_use = function(self, room, effect)
  -- effect.from 为使用者，effect.cards 为所选牌
  local room = effect.from.room
  room:throwCard(effect.cards, "zongheng", effect.from, effect.from)
  effect.from:drawCards(#effect.cards, "zongheng")
  end,
})

return skill_zongheng
