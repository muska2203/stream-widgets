"""Tests for the first-run setup helpers (frozen builds / --setup)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.interactive_story.config import Config
from apps.interactive_story.setup_wizard import (needs_setup, set_channel,
                                                 write_token)


class TestWriteToken(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = self.tmp / ".env"

    def test_creates_file(self):
        write_token(self.env, "oauth:abc")
        self.assertEqual(self.env.read_text(encoding="utf-8"),
                         "TWITCH_TOKEN=oauth:abc\n")

    def test_replaces_existing_key(self):
        self.env.write_text("# comment\nTWITCH_TOKEN=old\nOTHER=1\n",
                            encoding="utf-8")
        write_token(self.env, "oauth:new")
        self.assertEqual(self.env.read_text(encoding="utf-8"),
                         "# comment\nTWITCH_TOKEN=oauth:new\nOTHER=1\n")

    def test_appends_when_key_missing(self):
        self.env.write_text("OTHER=1\n", encoding="utf-8")
        write_token(self.env, "oauth:abc")
        self.assertEqual(self.env.read_text(encoding="utf-8"),
                         "OTHER=1\nTWITCH_TOKEN=oauth:abc\n")


class TestSetChannel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = self.tmp / "config.toml"

    def test_replaces_existing_key(self):
        self.cfg.write_text('channel = "old"\nround_duration = 25.0\n',
                            encoding="utf-8")
        set_channel(self.cfg, "new_chan")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"),
                         'channel = "new_chan"\nround_duration = 25.0\n')

    def test_adds_key_when_missing(self):
        self.cfg.write_text("round_duration = 25.0\n", encoding="utf-8")
        set_channel(self.cfg, "new_chan")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"),
                         'round_duration = 25.0\nchannel = "new_chan"\n')

    def test_creates_file(self):
        set_channel(self.cfg, "new_chan")
        self.assertEqual(self.cfg.read_text(encoding="utf-8"),
                         'channel = "new_chan"\n')


class TestNeedsSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = self.tmp / ".env"

    def test_mock_chat_needs_nothing(self):
        cfg = Config(mock_chat=True)
        self.assertFalse(needs_setup(cfg, self.env))

    def test_missing_channel(self):
        write_token(self.env, "oauth:abc")
        cfg = Config(mock_chat=False, channel="")
        self.assertTrue(needs_setup(cfg, self.env))

    def test_missing_token(self):
        cfg = Config(mock_chat=False, channel="someone")
        self.assertTrue(needs_setup(cfg, self.env))

    def test_complete_config(self):
        write_token(self.env, "oauth:abc")
        cfg = Config(mock_chat=False, channel="someone")
        self.assertFalse(needs_setup(cfg, self.env))


if __name__ == "__main__":
    unittest.main()
