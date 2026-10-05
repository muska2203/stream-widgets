"""Config loading: vote_mode default, accepted values, validation error."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.mini_rpg.config import VOTE_MODES, Config, load_config


class VoteModeTests(unittest.TestCase):
    def write_config(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".toml", delete=False, encoding="utf-8")
        self.addCleanup(Path(tmp.name).unlink)
        with tmp:
            tmp.write(text)
        return Path(tmp.name)

    def test_default_is_words(self):
        self.assertEqual(Config().vote_mode, "words")

    def test_autobattle_defaults(self):
        cfg = Config()
        self.assertFalse(hasattr(cfg, "combat_tick"))  # таймер раундов удалён
        self.assertEqual(cfg.hero_cooldown, 5.0)
        self.assertEqual(cfg.agility_cd_reduction, 0.5)
        self.assertEqual(cfg.min_cooldown, 1.0)
        self.assertEqual((cfg.chatter_cd_min, cfg.chatter_cd_max), (3.0, 8.0))
        self.assertEqual(cfg.chat_damage_pct, 5)
        self.assertEqual(cfg.chat_damage_cap_pct, 100)

    def test_missing_file_uses_default(self):
        cfg = load_config("no_such_config_file.toml")
        self.assertEqual(cfg.vote_mode, "words")

    def test_both_modes_load(self):
        self.assertEqual(VOTE_MODES, ("words", "classic"))
        for mode in VOTE_MODES:
            path = self.write_config(f'vote_mode = "{mode}"\n')
            self.assertEqual(load_config(path).vote_mode, mode)

    def test_unknown_mode_raises(self):
        path = self.write_config('vote_mode = "digits"\n')
        with self.assertRaises(ValueError) as ctx:
            load_config(path)
        self.assertIn("vote_mode", str(ctx.exception))

    def test_repo_config_loads(self):
        self.assertIn(load_config().vote_mode, VOTE_MODES)


if __name__ == "__main__":
    unittest.main()
