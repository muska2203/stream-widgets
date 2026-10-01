"""One combat encounter: hero vs mob with direction blocks (DESIGN.md).

Pure Python, no IO/timing/chat. The game loop (game.py) feeds chat choices
in turn by turn; Combat only resolves them and reports TurnResult structs
for the overlay.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from apps.mini_rpg.core.content import Mob
from apps.mini_rpg.core.hero import WEAPON_SLOTS, Hero

DIRECTIONS = ("head", "body", "legs")

LEVEL_SCALE = 0.15  # моб ×(1 + 0.15×(уровень героя − 1))


@dataclass
class TurnResult:
    actor: str              # "hero" | "mob"
    weapon: str | None      # melee/ranged у атаки героя
    direction: str | None   # направление атаки; None — ход пропущен
    blocked: bool
    damage: int
    crit: bool
    target_hp: int          # HP защищавшегося после хода


def scale_mob(mob: Mob, hero_level: int, level_scale: float = LEVEL_SCALE) -> Mob:
    """Mob scaled by hero level: hp/damage/rewards ×(1 + scale×(level−1)),
    rounded via int(x + 0.5) (half up)."""
    factor = 1 + level_scale * (hero_level - 1)
    return Mob(name=mob.name, icon=mob.icon,
               hp=int(mob.hp * factor + 0.5),
               damage_min=int(mob.damage_min * factor + 0.5),
               damage_max=int(mob.damage_max * factor + 0.5),
               xp=int(mob.xp * factor + 0.5),
               gold=int(mob.gold * factor + 0.5))


class Combat:
    def __init__(self, hero: Hero, mob: Mob, rng: random.Random,
                 level_scale: float = LEVEL_SCALE):
        self.hero = hero
        self.mob = scale_mob(mob, hero.level, level_scale)
        self.mob_hp = self.mob.hp
        self.rng = rng
        self.finished = False
        self.hero_won = False

    @property
    def rewards(self) -> tuple[int, int] | None:
        """Scaled (xp, gold) on victory; None while fighting or on defeat."""
        if self.finished and self.hero_won:
            return self.mob.xp, self.mob.gold
        return None

    def hero_turn(self, weapon: str, direction: str) -> TurnResult:
        """Hero attacks with weapon slot into direction; the mob secretly
        blocks one direction via rng. A ranged use is spent even on block."""
        self._check_active()
        if weapon not in WEAPON_SLOTS:
            raise ValueError(f"не оружейный слот: {weapon!r}")
        if direction not in DIRECTIONS:
            raise ValueError(f"неизвестное направление: {direction!r}")
        if getattr(self.hero, weapon) is None:
            raise ValueError(f"слот {weapon} пуст")
        blocked = self.rng.choice(DIRECTIONS) == direction
        damage, crit = (0, False)
        if not blocked:
            damage, crit = self.hero.roll_damage(weapon, self.rng)
            self.mob_hp = max(0, self.mob_hp - damage)
        if weapon == "ranged":
            self.hero.use_ranged()  # выстрелил — потратил, даже в блок
        result = TurnResult(actor="hero", weapon=weapon, direction=direction,
                            blocked=blocked, damage=damage, crit=crit,
                            target_hp=self.mob_hp)
        if self.mob_hp <= 0:
            self._finish(hero_won=True)
        return result

    def hero_skip(self) -> TurnResult:
        """No votes on attack — the hero does not strike, nothing is blocked."""
        self._check_active()
        return TurnResult(actor="hero", weapon=None, direction=None,
                          blocked=False, damage=0, crit=False,
                          target_hp=self.mob_hp)

    def mob_turn(self, defense: str | None) -> TurnResult:
        """Mob attacks a secret rng direction; defense is the chat's block
        direction (None = skipped, nothing is blocked). Unblocked damage is
        reduced by armor, minimum 0."""
        self._check_active()
        if defense is not None and defense not in DIRECTIONS:
            raise ValueError(f"неизвестное направление: {defense!r}")
        attack = self.rng.choice(DIRECTIONS)
        blocked = defense == attack
        damage = 0
        if not blocked:
            roll = self.rng.randint(self.mob.damage_min, self.mob.damage_max)
            damage = max(0, roll - self.hero.armor_value)
            self.hero.hp = max(0, self.hero.hp - damage)
        result = TurnResult(actor="mob", weapon=None, direction=attack,
                            blocked=blocked, damage=damage, crit=False,
                            target_hp=self.hero.hp)
        if self.hero.hp <= 0:
            self._finish(hero_won=False)
        return result

    def _finish(self, hero_won: bool) -> None:
        self.finished = True
        self.hero_won = hero_won

    def _check_active(self) -> None:
        if self.finished:
            raise RuntimeError("бой уже закончен")
