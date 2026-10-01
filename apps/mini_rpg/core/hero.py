"""Hero model: stats, XP/level, gold, HP/mana, 3 equipment slots.

Pure Python, no IO; rng is injected into the rolling methods. All balance
formulas (HP/mana/crit/damage) live here — one place to tune (DESIGN.md).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from apps.mini_rpg.core.content import SLOTS, Item

STATS = ("strength", "agility", "intellect", "endurance", "luck")

HP_PER_ENDURANCE = 5
MANA_PER_INTELLECT = 5
CRIT_PER_LUCK = 0.02
CRIT_MULTIPLIER = 2
XP_PER_LEVEL = 10

WEAPON_SLOTS = ("melee", "ranged")
DAMAGE_STAT = {"melee": "strength", "ranged": "agility"}


@dataclass
class Hero:
    base_hp: int
    strength: int = 0
    agility: int = 0
    intellect: int = 0
    endurance: int = 0
    luck: int = 0
    level: int = 1
    xp: int = 0
    gold: int = 0
    hp: int | None = None      # текущее; None = полное при создании
    mana: int | None = None
    melee: Item | None = None
    ranged: Item | None = None
    armor: Item | None = None

    def __post_init__(self):
        if self.hp is None:
            self.hp = self.max_hp
        if self.mana is None:
            self.mana = self.max_mana

    @property
    def max_hp(self) -> int:
        return self.base_hp + HP_PER_ENDURANCE * self.endurance

    @property
    def max_mana(self) -> int:
        return MANA_PER_INTELLECT * self.intellect

    @property
    def crit_chance(self) -> float:
        return CRIT_PER_LUCK * self.luck

    @property
    def armor_value(self) -> int:
        return self.armor.armor if self.armor is not None else 0

    @property
    def xp_to_next(self) -> int:
        return XP_PER_LEVEL * self.level

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def equip(self, item: Item) -> None:
        """Put item into its slot; the replaced item is lost."""
        if item.slot not in SLOTS:
            raise ValueError(f"неизвестный слот: {item.slot!r}")
        setattr(self, item.slot, item)

    def gain_xp(self, amount: int) -> int:
        """Add XP; returns how many levels were gained (threshold 10×level
        is subtracted, several levels can come from one kill)."""
        self.xp += amount
        ups = 0
        while self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            ups += 1
        return ups

    def level_up(self, stat: str) -> None:
        """+1 to a stat; endurance also heals +5 current HP with the max."""
        if stat not in STATS:
            raise ValueError(f"неизвестная стата: {stat!r}")
        setattr(self, stat, getattr(self, stat) + 1)
        if stat == "endurance":
            self.hp += HP_PER_ENDURANCE

    def use_ranged(self) -> None:
        """Spend one ranged use; at zero the weapon breaks (slot empties)."""
        if self.ranged is None:
            raise ValueError("нет дальнего оружия")
        self.ranged.uses -= 1
        if self.ranged.uses <= 0:
            self.ranged = None

    def roll_damage(self, slot: str, rng: random.Random) -> tuple[int, bool]:
        """Weapon roll N..M + stat, crit ×2 of the total; (damage, crit)."""
        if slot not in WEAPON_SLOTS:
            raise ValueError(f"не оружейный слот: {slot!r}")
        weapon = getattr(self, slot)
        if weapon is None:
            raise ValueError(f"слот {slot} пуст")
        damage = rng.randint(weapon.damage_min, weapon.damage_max)
        damage += getattr(self, DAMAGE_STAT[slot])
        crit = rng.random() < self.crit_chance
        if crit:
            damage *= CRIT_MULTIPLIER
        return damage, crit


def new_hero(base_hp: int) -> Hero:
    """Level-1 hero with the starter kit: fists (melee 1–2), no ranged/armor."""
    hero = Hero(base_hp=base_hp)
    hero.equip(Item(name="Кулаки", icon="👊", slot="melee", damage_min=1,
                    damage_max=2, uses=None, armor=None, price=0))
    return hero
