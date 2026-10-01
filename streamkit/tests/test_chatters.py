"""Tests for the chatter registry: session priority, persistence, fallbacks."""

from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from streamkit import ChatterRegistry


class ChatterRegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "chatters.json"

    def test_pick_prefers_session_over_base(self):
        reg = ChatterRegistry()
        reg.all.update({"old1", "old2"})  # база «прошлых стримов», вне сессии
        reg.add("active1")
        rng = random.Random(1)
        picks = {reg.pick(rng) for _ in range(50)}
        self.assertEqual(picks, {"active1"})

    def test_pick_falls_back_to_base(self):
        reg = ChatterRegistry()
        reg.all.update({"old1", "old2"})
        rng = random.Random(1)
        picks = {reg.pick(rng) for _ in range(50)}
        self.assertEqual(picks, {"old1", "old2"})

    def test_pick_empty_base_returns_none(self):
        self.assertIsNone(ChatterRegistry().pick(random.Random(1)))

    def test_add_dedupes_and_ignores_empty(self):
        reg = ChatterRegistry()
        reg.add("nick")
        reg.add("nick")
        reg.add("   ")
        reg.add("")
        self.assertEqual(len(reg), 1)
        self.assertEqual(reg.session, ["nick"])

    def test_persistence_roundtrip(self):
        reg = ChatterRegistry(self.path)
        reg.add("beta")
        reg.add("alpha")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["chatters"], ["alpha", "beta"])  # sorted
        loaded = ChatterRegistry(self.path)
        self.assertEqual(loaded.all, {"alpha", "beta"})
        self.assertEqual(loaded.session, [])  # сессия не персистится

    def test_missing_file_starts_empty(self):
        reg = ChatterRegistry(self.path)
        self.assertEqual(len(reg), 0)

    def test_broken_file_starts_empty_and_keeps_working(self):
        self.path.write_text("это не json", encoding="utf-8")
        reg = ChatterRegistry(self.path)
        self.assertEqual(len(reg), 0)
        reg.add("nick")  # save() перезаписывает битый файл
        self.assertEqual(len(reg), 1)
        self.assertEqual(ChatterRegistry(self.path).all, {"nick"})

    def test_memory_only_registry_writes_nothing(self):
        reg = ChatterRegistry()
        reg.add("nick")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
