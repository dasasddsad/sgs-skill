-- 技能：铁壁（tiebi）｜类型：trigger
-- 由「三国杀 Agent」自动生成，请人工核对结算细节
local skill_tiebi = fk.CreateSkill({ name = "tiebi" })

skill_tiebi:addEffect(fk.Damaged, {
  anim_type = "masochism",
  on_use = function(self, event, target, player, data)
  -- 受击结算：伤害来源判定 + 摸牌
  local room = player.room
  local from = data.from
  if from and not from.dead then
    room:doIndicate(player.id, { from.id })
  end
  room:notifySkillInvoked(player, "tiebi", "masochism")
  player:drawCards(1, "tiebi")
  end,
})

return skill_tiebi
