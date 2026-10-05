"""One combat encounter: hero vs mob auto-battle with a chat squad
(DESIGN.md), continuous-time with per-unit cooldowns.

No votes in combat: every unit (hero / mob / each active squad chatter) has
its own attack cooldown; when cd_left reaches 0 the unit attacks and its
cd_left is topped up by its cooldown (the remainder is kept, so big frames
resolve several attacks). The hero hits with random melee damage (+ strength,
crit ×2); chatters hit for random damage without crit; the mob hits only the
hero (chatters have no HP and are invulnerable), the hero's flat armor
absorbs part of the hit, minimum 0. There is no dodge. Chatters join the
squad once per combat with the «бой» command; each chatter is calibrated so
his DPS ≈ chat_pct% of the hero's average DPS, and at most cap // pct squad
members actually attack — the rest stand on the field inactive.

Pure Python, no IO/timing/chat (join() only prints a console note when the
squad is full). The game loop (game.py) drives update(dt) every frame and
feeds join() from chat; Combat resolves them and reports CombatEvent structs
for the overlay.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass

from apps.mini_rpg.core.content import Mob
from apps.mini_rpg.core.hero import Hero

LEVEL_SCALE = 0.15  # моб ×(1 + 0.15×(уровень героя − 1))

# пул эмодзи членов отряда (выбор детерминирован ником — стабильный хеш)
CHATTER_EMOJI = ("🐶", "🐹", "🐰", "🦇", "🐝", "🦄", "🐲", "🐙", "🦀", "🐌",
                 "🐞", "🦜", "🐧", "🦆", "🦅", "🐗", "🐍", "🦎", "🐳", "🦈")


@dataclass
class ChatterUnit:
    nick: str
    emoji: str          # детерминированно из ника (хеш → CHATTER_EMOJI)
    damage_min: int
    damage_max: int
    cooldown: float
    cd_left: float
    active: bool        # False = сверх капа, стоит на поле, не атакует


@dataclass
class CombatEvent:
    seq: int            # монотонный счётчик событий боя
    attacker: str       # "hero" | "mob" | ник чаттера
    target: str         # "mob" | "hero"
    damage: int         # итоговый урон по цели
    crit: bool          # только у героя
    armor_absorbed: int  # только удар моба → герой
    target_hp: int      # HP цели после удара


def scale_mob(mob: Mob, hero_level: int, level_scale: float = LEVEL_SCALE) -> Mob:
    """Mob scaled by hero level: hp/damage/rewards ×(1 + scale×(level−1)),
    rounded via int(x + 0.5) (half up). Cooldown is not scaled."""
    factor = 1 + level_scale * (hero_level - 1)
    return Mob(name=mob.name, icon=mob.icon,
               hp=int(mob.hp * factor + 0.5),
               damage_min=int(mob.damage_min * factor + 0.5),
               damage_max=int(mob.damage_max * factor + 0.5),
               xp=int(mob.xp * factor + 0.5),
               gold=int(mob.gold * factor + 0.5),
               cooldown=mob.cooldown)


class Combat:
    def __init__(self, hero: Hero, mob: Mob, rng: random.Random,
                 hero_cooldown: float = 5.0, agility_cd_reduction: float = 0.5,
                 min_cooldown: float = 1.0, chatter_cd_min: float = 3.0,
                 chatter_cd_max: float = 8.0,
                 chat_pct: int = 5, chat_cap: int = 100,
                 level_scale: float = LEVEL_SCALE):
        self.hero = hero
        self.mob = scale_mob(mob, hero.level, level_scale)
        self.mob_hp = self.mob.hp
        self.rng = rng
        self.hero_cd = hero.attack_cooldown(hero_cooldown,
                                            agility_cd_reduction, min_cooldown)
        self.hero_cd_left = self.hero_cd   # полный КД от начала боя
        self.mob_cd_left = self.mob.cooldown
        self.chatter_cd_min = chatter_cd_min
        self.chatter_cd_max = chatter_cd_max
        self.chat_pct = chat_pct
        self.chat_cap = chat_cap
        self.squad: list[ChatterUnit] = []  # порядок = порядок вступления
        self.finished = False
        self.hero_won = False
        self._event_seq = 0

    @property
    def rewards(self) -> tuple[int, int] | None:
        """Scaled (xp, gold) on victory; None while fighting or on defeat."""
        if self.finished and self.hero_won:
            return self.mob.xp, self.mob.gold
        return None

    def join(self, user: str) -> bool:
        """Chatter joins the squad (once per combat); False if already in
        or the combat is over. Creates the ChatterUnit even over the cap
        (active=False — visible on the field, doesn't attack)."""
        if self.finished or any(u.nick == user for u in self.squad):
            return False
        unit = self._roll_chatter(user)
        self.squad.append(unit)
        if not unit.active:
            print(f"squad full ({self.chat_cap // self.chat_pct} attackers): "
                  f"{user} stands by", flush=True)
        return True

    def _roll_chatter(self, user: str) -> ChatterUnit:
        """Random but calibrated chatter: DPS = chat_pct% of the hero's
        average DPS; damage range fitted to the rolled cooldown, minimum
        single-hit damage 1."""
        lo, hi = self.hero.damage_range()
        hero_dps = (lo + hi) / 2 / self.hero_cd
        target_dps = hero_dps * self.chat_pct / 100
        cd = self.rng.uniform(self.chatter_cd_min, self.chatter_cd_max)
        avg = target_dps * cd
        dmg_lo = max(1, int(avg))
        dmg_hi = max(dmg_lo, 2 * round(avg) - dmg_lo)  # среднее (lo+hi)/2 ≈ avg
        attackers = sum(1 for u in self.squad if u.active)
        return ChatterUnit(
            nick=user,
            emoji=CHATTER_EMOJI[zlib.crc32(user.encode("utf-8"))
                                % len(CHATTER_EMOJI)],
            damage_min=dmg_lo, damage_max=dmg_hi, cooldown=cd,
            cd_left=self.rng.uniform(0, cd),  # стартовый разброс
            active=attackers < self.chat_cap // self.chat_pct)

    def update(self, dt: float) -> list[CombatEvent]:
        """Advance all cooldowns by dt and resolve attacks in a fixed order:
        hero → chatters (join order) → mob. Returns the frame's events;
        when a death ends the combat, the frame's remaining attacks are
        cancelled."""
        self._check_active()
        events: list[CombatEvent] = []
        self.hero_cd_left -= dt
        for unit in self.squad:
            if unit.active:
                unit.cd_left -= dt
        self.mob_cd_left -= dt
        while self.hero_cd_left <= 0:
            events.append(self._hero_hit())
            self.hero_cd_left += self.hero_cd
            if self.finished:
                return events
        for unit in self.squad:
            if not unit.active:
                continue
            while unit.cd_left <= 0:
                events.append(self._chatter_hit(unit))
                unit.cd_left += unit.cooldown
                if self.finished:
                    return events
        while self.mob_cd_left <= 0:
            events.append(self._mob_hit())
            self.mob_cd_left += self.mob.cooldown
            if self.finished:
                return events
        return events

    def _hero_hit(self) -> CombatEvent:
        damage, crit = self.hero.strike(self.rng)
        self.mob_hp = max(0, self.mob_hp - damage)
        if self.mob_hp <= 0:
            self._finish(hero_won=True)
        return self._event("hero", "mob", damage, crit, 0, self.mob_hp)

    def _chatter_hit(self, unit: ChatterUnit) -> CombatEvent:
        damage = self.rng.randint(unit.damage_min, unit.damage_max)
        self.mob_hp = max(0, self.mob_hp - damage)
        if self.mob_hp <= 0:
            self._finish(hero_won=True)
        return self._event(unit.nick, "mob", damage, False, 0, self.mob_hp)

    def _mob_hit(self) -> CombatEvent:
        roll = self.rng.randint(self.mob.damage_min, self.mob.damage_max)
        absorbed = min(roll, self.hero.armor_value)
        damage = roll - absorbed
        self.hero.hp = max(0, self.hero.hp - damage)
        if self.hero.hp <= 0:
            self._finish(hero_won=False)
        return self._event("mob", "hero", damage, False, absorbed,
                           self.hero.hp)

    def _event(self, attacker: str, target: str, damage: int, crit: bool,
               armor_absorbed: int, target_hp: int) -> CombatEvent:
        self._event_seq += 1
        return CombatEvent(seq=self._event_seq, attacker=attacker,
                           target=target, damage=damage, crit=crit,
                           armor_absorbed=armor_absorbed, target_hp=target_hp)

    def _finish(self, hero_won: bool) -> None:
        self.finished = True
        self.hero_won = hero_won

    def _check_active(self) -> None:
        if self.finished:
            raise RuntimeError("бой уже закончен")
