"""Hero model: stats, XP/level, gold, HP/mana, 2 equipment slots.

Pure Python, no IO; rng is injected into the rolling methods. All balance
formulas (HP/mana/crit/attack cooldown/damage) live here — one place to tune
(DESIGN.md).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from apps.mini_rpg.core.content import SLOTS, DEFAULT_STARTER, Item

STATS = ("strength", "agility", "intellect", "endurance", "luck")

HP_PER_ENDURANCE = 5
MANA_PER_INTELLECT = 5
CRIT_PER_LUCK = 0.02
CRIT_MULTIPLIER = 2
XP_PER_LEVEL = 10


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
        """Flat damage absorbed from every mob hit; 0 without armor."""
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

    def damage_range(self) -> tuple[int, int]:
        """Melee weapon damage range (lo, hi) = damage_min/max + strength."""
        if self.melee is None:
            raise ValueError("слот melee пуст")
        return (self.melee.damage_min + self.strength,
                self.melee.damage_max + self.strength)

    def attack_cooldown(self, base: float, per_agility: float,
                        min_cd: float) -> float:
        """Attack cooldown: base − agility × per_agility, floored at min_cd.
        Fixed for the whole combat (Combat snapshots it at start)."""
        return max(min_cd, base - self.agility * per_agility)

    def strike(self, rng: random.Random) -> tuple[int, bool]:
        """Auto-combat hit: random damage in damage_range with a crit roll
        ×2 of the total; (damage, crit)."""
        lo, hi = self.damage_range()
        damage = rng.randint(lo, hi)
        crit = rng.random() < self.crit_chance
        if crit:
            damage *= CRIT_MULTIPLIER
        return damage, crit


def new_hero(base_hp: int, starters: list[Item] | None = None) -> Hero:
    """Level-1 hero with the starter kit: starter items (из пула items/ —
    предметы со starter = true, по одному на слот; фолбэк [DEFAULT_STARTER]).
    Экипируются копии — пул и дефолт не мутируют."""
    hero = Hero(base_hp=base_hp)
    for item in (starters if starters is not None else [DEFAULT_STARTER]):
        hero.equip(replace(item))
    return hero
