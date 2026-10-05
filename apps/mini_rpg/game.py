"""Game state machine: RUN_START -> EVENT -> (COMBAT | SHOP | REST) ->
(LEVELUP) -> EVENT -> ... -> GAME_OVER -> EVENT (docs/DESIGN.md).

Pure Python: all timing runs through update(dt) called from the main loop
(main.py, этап 8); chat enters via the single handle_chat_message(). The
overlay is a listener with the NullUI interface below (webui.py, этап 6);
until then the game runs blind and state is readable from attributes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from pathlib import Path

from streamkit import ChatterRegistry, VoteLoop, VoteWords

from apps.mini_rpg.config import Config
from apps.mini_rpg.core import (DEFAULT_ITEMS_DIR, DEFAULT_MOBS_DIR,
                                DEFAULT_PREFIXES, DEFAULT_PREFIXES_PATH,
                                Combat, CombatEvent, ContentError, Hero, Item,
                                Mob, door_commands, find_starters,
                                levelup_choice, levelup_commands, load_items,
                                load_mobs, load_prefixes, new_hero, scale_mob,
                                shop_commands)
from apps.mini_rpg.persistence import load_checkpoint, save_checkpoint

RUN_START, EVENT, COMBAT, SHOP, REST, LEVELUP, GAME_OVER, ERROR = (
    "run_start", "event", "combat", "shop", "rest", "levelup", "game_over",
    "error")

# combat sub-phases (Game.state == COMBAT)
FIGHT, COMBAT_END = "fight", "end"

# команда вступления в отряд автобоя (один раз за бой на чаттера)
JOIN_COMMAND = "бой"

DOORS = 3

MOB, SHOP_KIND, REST_KIND = "mob", "shop", "rest"
MOB_CHANCE = 0.7  # шанс подтипа «враг» на дверь; остальное — интерактив
DOOR_VIEW = {SHOP_KIND: ("🏪", "Магазин"), REST_KIND: ("🛏️", "Зона отдыха")}


@dataclass(frozen=True)
class Door:
    """One event door: a kind plus the concrete mob for kind == "mob"."""
    kind: str  # MOB | SHOP_KIND | REST_KIND
    mob: Mob | None = None

    @property
    def icon(self) -> str:
        return self.mob.icon if self.kind == MOB else DOOR_VIEW[self.kind][0]

    @property
    def name(self) -> str:
        return self.mob.name if self.kind == MOB else DOOR_VIEW[self.kind][1]


class NullUI:
    """No-op overlay listener — the seam for webui.WebUI (этап 6).

    Game pushes every phase change and vote update here; state details are
    readable from the Game attributes passed as arguments.
    """

    def show_event(self, doors: list[Door]) -> None:
        pass

    def show_combat(self, combat: Combat, phase: str) -> None:
        pass

    def show_combat_events(self, events: list[CombatEvent]) -> None:
        """Attacks resolved during one frame of the fight."""
        pass

    def show_shop(self, items: list[Item]) -> None:
        pass

    def show_rest(self, hero: Hero) -> None:
        pass

    def show_levelup(self, hero: Hero) -> None:
        pass

    def show_gameover(self, summary: dict) -> None:
        pass

    def show_error(self, message: str) -> None:
        pass

    def update_votes(self, counts: dict[str, int], leaders: list[str]) -> None:
        pass

    def show_tie_resolve(self, leaders: list[str], winner: str) -> None:
        """Tie at round end: roulette among the leaders lands on winner."""
        pass

    def update_timer(self) -> None:
        """Per-frame push of the phase timer (WebUI republishes on change)."""
        pass


class Game:
    def __init__(self, cfg: Config, ui: NullUI | None = None,
                 mobs_dir: str | Path = DEFAULT_MOBS_DIR,
                 items_dir: str | Path = DEFAULT_ITEMS_DIR,
                 prefixes_path: str | Path = DEFAULT_PREFIXES_PATH,
                 chatters: ChatterRegistry | None = None,
                 save_path: str | Path | None = None):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.ui = ui or NullUI()
        self.mobs_dir = mobs_dir
        self.items_dir = items_dir
        self.prefixes_path = prefixes_path
        # None → реестр только в памяти (тесты); файл решает main.py
        # (не `or`: у ChatterRegistry есть __len__, пустой реестр falsy)
        self.chatters = chatters if chatters is not None else ChatterRegistry()
        # None → без персиста прогресса (мок/smoke/тесты); файл решает main.py
        self.save_path = Path(save_path) if save_path is not None else None
        self.state = ""
        self.vote_loop: VoteLoop | None = None
        # зрители голосуют командами-алиасами канонических ключей (цифр):
        # vote_mode "words" — случайное слово раунда из пула streamkit,
        # "classic" — фиксированная команда из таблиц core.choices;
        # UI показывает алиас (word), VoteLoop считает канонические ключи
        self.vote_words = (VoteWords.from_file(rng=self.rng)
                           if cfg.vote_mode == "words" else None)
        self.vote_key_words: dict[str, str] = {}  # ключ -> алиас текущего раунда
        self.hero: Hero | None = None
        self.doors: list[Door] = []
        self.items_pool: list[Item] = []   # перечитывается на каждом EVENT
        self.prefixes: list[str] = list(DEFAULT_PREFIXES)  # там же
        self.shop_items: list[Item] = []   # товары текущего магазина
        self.combat: Combat | None = None
        self.combat_phase = ""
        self.pending_levelups = 0
        self.kills = 0                 # убито мобов за забег
        self.gold_earned = 0           # заработано золота за забег
        self.deaths = 0                # смертей героя за забег
        self.defeated: list[str] = []  # боевые клички поверженных за забег
        self.run_summary: dict | None = None
        self.error_message = ""
        self.time_left = 0.0           # единый countdown текущей фазы
        self.overtime = False          # овертайм текущего голосования (0 голосов)
        # отложенный коллбэк конца раунда на время рулетки при ничьей
        self._pending_end = None
        restored = (load_checkpoint(self.save_path)
                    if self.save_path is not None else None)
        if restored is not None:
            self.hero = restored["hero"]
            self.kills = restored["kills"]
            self.gold_earned = restored["gold_earned"]
            self.deaths = restored["deaths"]
            self.defeated = restored["defeated"]
            self.pending_levelups = restored["pending_levelups"]
            print(f"progress restored: level {self.hero.level}, "
                  f"kills {self.kills}, gold {self.hero.gold}", flush=True)
            self.enter_event()  # свежий бросок дверей, бой не восстанавливаем
        else:
            self.enter_run_start()

    # --- run / event -----------------------------------------------------

    def enter_run_start(self) -> None:
        """Very first run (no save): fresh level-1 hero, first event."""
        self.state = RUN_START
        try:
            starters = find_starters(load_items(self.items_dir))
        except ContentError as e:
            self._enter_error(f"Ошибка пула предметов: {e}")
            return
        self.hero = new_hero(self.cfg.base_hp, starters)
        self.kills = 0
        self.gold_earned = 0
        self.deaths = 0
        self.defeated = []
        self.pending_levelups = 0
        self.run_summary = None
        self._save_checkpoint()
        print("new run started", flush=True)
        self.enter_event()

    def enter_event(self) -> None:
        """3 doors with mixed events; pools and prefixes reload on entry."""
        self.combat = None
        try:
            mobs = load_mobs(self.mobs_dir)
        except ContentError as e:
            self._enter_error(f"Ошибка пула мобов: {e}")
            return
        if not mobs:
            self._enter_error("Пул мобов пуст — положите .toml "
                              f"в {self.mobs_dir}")
            return
        try:
            # стартовые предметы (starter = true) в магазин не попадают
            self.items_pool = [it for it in load_items(self.items_dir)
                               if not it.starter]
        except ContentError as e:
            self._enter_error(f"Ошибка пула предметов: {e}")
            return
        try:
            self.prefixes = load_prefixes(self.prefixes_path)
        except ContentError as e:
            self._enter_error(f"Ошибка файла префиксов: {e}")
            return
        self.doors = self._roll_doors(mobs)
        self.state = EVENT
        # чекпоинт на границе фаз: всё, что меняло героя (бой/магазин/
        # отдых/прокачка), к этому моменту уже отыграно
        self._save_checkpoint()
        self._open_door_vote()

    def _roll_doors(self, mobs: list[Mob]) -> list[Door]:
        """Subtype per door first — mob with MOB_CHANCE, else an interactive
        (rest always, shop only if the item pool is non-empty) — then mob
        doors filled with distinct mobs while the pool lasts
        (DESIGN.md «Типы событий»)."""
        interactives = [REST_KIND] + ([SHOP_KIND] if self.items_pool else [])
        rolled = [MOB if self.rng.random() < MOB_CHANCE
                  else self.rng.choice(interactives) for _ in range(DOORS)]
        sample = self.rng.sample(mobs, min(rolled.count(MOB), len(mobs)))
        while len(sample) < rolled.count(MOB):
            sample.append(self.rng.choice(mobs))
        it = iter(sample)
        # Моб скейлится под уровень героя уже на дверях — оверлей показывает
        # threat ровно с теми числами, с которыми начнётся бой.
        return [Door(kind, scale_mob(next(it), self.hero.level)
                     if kind == MOB else None)
                for kind in rolled]

    def _open_door_vote(self) -> None:
        validate = self._assign_words(door_commands())
        self.ui.show_event(self.doors)
        self._open_vote(self.cfg.event_duration, validate, self.on_door_end)

    def on_door_end(self, winner: str | None, counts: dict[str, int],
                    n_voters: int) -> None:
        # winner всегда есть: 0 голосов разруливает овертайм/рулетка в
        # _resolve_end (единое поведение всех голосований)
        door = self.doors[int(winner) - 1]
        print(f"door {winner}: {door.name} ({n_voters} voters)", flush=True)
        if door.kind == MOB:
            self.enter_combat(door.mob)
        elif door.kind == SHOP_KIND:
            self.enter_shop()
        else:
            self.enter_rest()

    def _save_checkpoint(self) -> None:
        """Persist hero + run counters; no-op without a save_path (mock/
        smoke/tests). Save errors only warn — the stream never crashes."""
        if self.save_path is not None:
            save_checkpoint(self.save_path, self)

    # --- combat ----------------------------------------------------------

    def enter_combat(self, mob: Mob) -> None:
        # mob уже отскейлен при броске дверей — без повторного скейла.
        # Боевая кличка присваивается копией (replace): дверной mob не трогаем;
        # Combat скопирует её дальше через scale_mob(level_scale=0).
        mob = replace(mob, name=self._battle_name(mob))
        self.combat = Combat(self.hero, mob, self.rng,
                             hero_cooldown=self.cfg.hero_cooldown,
                             agility_cd_reduction=self.cfg.agility_cd_reduction,
                             min_cooldown=self.cfg.min_cooldown,
                             chatter_cd_min=self.cfg.chatter_cd_min,
                             chatter_cd_max=self.cfg.chatter_cd_max,
                             chat_pct=self.cfg.chat_damage_pct,
                             chat_cap=self.cfg.chat_damage_cap_pct,
                             level_scale=0)
        self.state = COMBAT
        self.combat_phase = FIGHT
        self.vote_loop = None
        # глобального таймера в бою нет — кулдаун у каждого юнита; 0 замораживает
        # републикации update_timer (WebUI публикует только по смене секунды)
        self.time_left = 0.0
        self.ui.show_combat(self.combat, FIGHT)
        print(f"combat started: {mob.name} (hero hp {self.hero.hp})",
              flush=True)

    def _battle_name(self, mob: Mob) -> str:
        """«Префикс Ник»; без базы чаттеров — «Префикс Тип»."""
        prefix = self.rng.choice(self.prefixes)
        nick = self.chatters.pick(self.rng)
        if nick is not None:
            return f"{prefix} {nick}"
        return f"{prefix} {mob.name}"

    def _finish_combat(self) -> None:
        if not self.combat.hero_won:
            self.enter_game_over()
            return
        xp, gold = self.combat.rewards
        self.kills += 1
        self.gold_earned += gold
        self.defeated.append(self.combat.mob.name)
        self.hero.gold += gold
        self.pending_levelups = self.hero.gain_xp(xp)
        print(f"combat won: +{xp} xp, +{gold} gold "
              f"(kills {self.kills})", flush=True)
        if self.pending_levelups:
            self.enter_levelup()
        else:
            self._enter_combat_end()

    def _enter_combat_end(self) -> None:
        """Short pause after a won combat (and its levelups) before EVENT."""
        self.state = COMBAT
        self.combat_phase = COMBAT_END
        self.vote_loop = None
        self.time_left = self.cfg.combat_end_pause

    # --- shop --------------------------------------------------------------

    def enter_shop(self) -> None:
        """Up to 9 distinct items the hero can afford; 0 = exit."""
        affordable = [it for it in self.items_pool
                      if it.price <= self.hero.gold]
        self.shop_items = self.rng.sample(affordable,
                                          min(9, len(affordable)))
        self.state = SHOP
        validate = self._assign_words(shop_commands(len(self.shop_items)))
        self.ui.show_shop(self.shop_items)
        self._open_vote(self.cfg.shop_duration, validate, self.on_shop_end)

    def on_shop_end(self, winner: str | None, counts: dict[str, int],
                    n_voters: int) -> None:
        if winner == "0":
            print("shop closed without purchase", flush=True)
        else:
            item = self.shop_items[int(winner) - 1]
            self.hero.gold -= item.price
            self.hero.equip(replace(item))  # копия: пул не мутирует
            print(f"shop: bought {item.name} for {item.price} "
                  f"({n_voters} voters)", flush=True)
        self.vote_loop = None
        self.time_left = self.cfg.combat_end_pause

    # --- rest ----------------------------------------------------------------

    def enter_rest(self) -> None:
        """Full HP/mana restore, short pause, back to EVENT; no votes."""
        self.hero.hp = self.hero.max_hp
        self.hero.mana = self.hero.max_mana
        self.state = REST
        self.vote_loop = None
        self.time_left = self.cfg.combat_end_pause
        self.ui.show_rest(self.hero)
        print("rest: hp/mana fully restored", flush=True)

    # --- levelup ---------------------------------------------------------

    def enter_levelup(self) -> None:
        self.state = LEVELUP
        self._open_levelup_vote()

    def _open_levelup_vote(self) -> None:
        validate = self._assign_words(levelup_commands())
        self.ui.show_levelup(self.hero)
        self._open_vote(self.cfg.levelup_duration, validate,
                        self.on_levelup_end)

    def on_levelup_end(self, winner: str | None, counts: dict[str, int],
                       n_voters: int) -> None:
        stat = levelup_choice(winner)
        self.hero.level_up(stat)
        self.pending_levelups -= 1
        print(f"levelup: {stat} +1 ({n_voters} voters)", flush=True)
        if self.pending_levelups:
            self.enter_levelup()
        else:
            self._enter_combat_end()

    # --- game over / error -------------------------------------------------

    def enter_game_over(self) -> None:
        """Death: summary screen, then the run continues with the same hero.
        Penalty: gold and current-level XP are lost and the run counters
        (kills, gold earned, defeated) reset — the summary screen shows
        them captured before the reset; level/stats/gear and the deaths
        counter are kept. The hero revives at full HP/mana and the
        penalized state is persisted at once."""
        self.state = GAME_OVER
        self.vote_loop = None
        self.time_left = self.cfg.gameover_pause
        self.deaths += 1
        self.run_summary = {"kills": self.kills,
                            "gold_earned": self.gold_earned,
                            "defeated": list(self.defeated)}
        self.kills = 0
        self.gold_earned = 0
        self.defeated = []
        self.hero.gold = 0
        self.hero.xp = 0
        self.hero.hp = self.hero.max_hp
        self.hero.mana = self.hero.max_mana
        self._save_checkpoint()  # прогресс пишется уже после сброса
        self.ui.show_gameover(self.run_summary)
        print(f"game over: {self.run_summary} (gold/xp lost, "
              "run stats reset)", flush=True)

    def _respawn(self) -> None:
        """Back from the summary screen: the run goes on, fresh event."""
        self.run_summary = None
        self.enter_event()

    def _enter_error(self, message: str) -> None:
        self.state = ERROR
        self.vote_loop = None
        self.error_message = message
        self.ui.show_error(message)
        print(f"error: {message}", flush=True)

    # --- chat ------------------------------------------------------------

    def handle_chat_message(self, user: str, text: str) -> None:
        """Single entry point for chat commands (mock chat or Twitch)."""
        # любой написавший попадает в базу чаттеров — до фильтрации по фазе
        self.chatters.add(user)
        # вступление в отряд автобоя — не голосование, vote_loop в бою нет
        if self.state == COMBAT and self.combat_phase == FIGHT and \
                self.combat is not None and \
                text.strip().lower() == JOIN_COMMAND:
            if self.combat.join(user):
                self.ui.show_combat(self.combat, FIGHT)
            return
        if self.vote_loop is None or not self.vote_loop.active:
            return
        if self.vote_loop.vote(user, text):
            leaders, _ = self.vote_loop.leaders()
            self.ui.update_votes(self.vote_loop.counts(), leaders)

    # --- per-frame ---------------------------------------------------------

    def update(self, dt: float) -> None:
        if self.state not in (EVENT, COMBAT, SHOP, REST, LEVELUP, GAME_OVER):
            return  # RUN_START транзитный, ERROR ждёт починки пула
        if self.state == COMBAT and self.combat_phase == FIGHT:
            # бой продвигается каждый кадр (per-unit кулдауны), таймера фазы
            # нет — update_timer не зовём, публикации идут от событий боя
            events = self.combat.update(dt)
            if events:
                self.ui.show_combat_events(events)
            if self.combat.finished:
                self._finish_combat()
            return
        self.time_left -= dt
        self.ui.update_timer()
        if self.time_left > 0:
            return
        if self._pending_end is not None:
            # рулетка при ничьей отыграла — применяем отложенный исход;
            # в UI из подсвеченных лидеров остаётся один победитель
            on_end, winner, counts, n_voters = self._pending_end
            self._pending_end = None
            self.ui.update_votes(counts, [winner])
            on_end(winner, counts, n_voters)
        elif self.vote_loop is not None:
            # коллбэк может сменить фазу и обнулить vote_loop — не трогаем
            # его после finish()
            self.vote_loop.finish()
        elif self.state == COMBAT and self.combat_phase == COMBAT_END:
            self.enter_event()
        elif self.state in (SHOP, REST):
            self.enter_event()
        elif self.state == GAME_OVER:
            self._respawn()

    def _assign_words(self, classic: dict[str, str]):
        """Build the round's alias table (key -> chat command) and return
        the validator (command -> key). vote_mode "words": a random word
        per key via VoteWords; "classic": the fixed commands from
        core.choices (`classic` = {key: command}). Runs BEFORE the
        ui.show_* call of the phase so the overlay gets the aliases in the
        same snapshot."""
        if self.vote_words is not None:
            mapping = self.vote_words.assign(list(classic))
            self.vote_key_words = {key: word for word, key in mapping.items()}
        else:
            self.vote_key_words = dict(classic)
            mapping = {command: key for key, command in classic.items()}
        return VoteWords.validator(mapping)

    def current_vote_words(self) -> list[str]:
        """Chat commands of the currently open vote (pool for the mock
        chat; random words in "words" mode, classic commands otherwise).
        During the auto-battle — the squad join command."""
        if self.state == COMBAT and self.combat_phase == FIGHT:
            return [JOIN_COMMAND]
        return list(self.vote_key_words.values())

    def _open_vote(self, duration: float, validate, on_end) -> None:
        """Fresh VoteLoop per phase with its own validator; the phase timer
        lives in Game (time_left), the round is closed by an explicit
        finish() when it runs out."""
        self.time_left = duration
        self.overtime = False
        self.vote_loop = VoteLoop(
            duration,
            lambda w, c, n: self._resolve_end(on_end, w, c, n),
            validate=validate, rng=self.rng)

    def _resolve_end(self, on_end, winner: str | None,
                     counts: dict[str, int], n_voters: int) -> None:
        """Round-end wrapper, uniform for every vote (docs/DESIGN.md
        «Овертайм»): 0 votes triggers a one-shot overtime — the same vote
        (same words, same options) continues for overtime_duration. If
        overtime also ends with 0 votes, a random winner among ALL options
        is resolved by the same roulette as a tie; a single leader applies
        at once; a tie holds the phase for tie_resolve_pause while the
        overlay runs the roulette (show_tie_resolve), then update() applies
        the pending outcome."""
        if winner is None and not self.overtime:
            self.overtime = True
            self.time_left = self.cfg.overtime_duration
            # свежий VotingRound с тем же валидатором: слова раунда и
            # варианты сохраняются, голосов всё равно не было
            self.vote_loop.start()
            print("no votes, overtime", flush=True)
            return
        if winner is None:  # овертайм тоже без голосов
            leaders = sorted(self.vote_key_words)
            winner = self.rng.choice(leaders)
            reason = f"no votes after overtime, random among {leaders}"
        else:
            top = max(counts.values())
            leaders = sorted(k for k, v in counts.items() if v == top)
            reason = f"tie {leaders}"
        self.overtime = False
        if len(leaders) < 2:
            on_end(winner, counts, n_voters)
            return
        self.vote_loop = None
        self.time_left = self.cfg.tie_resolve_pause
        self._pending_end = (on_end, winner, counts, n_voters)
        print(f"{reason} -> {winner}, resolving ({n_voters} voters)",
              flush=True)
        self.ui.show_tie_resolve(leaders, winner)
