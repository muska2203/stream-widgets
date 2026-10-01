"""Tests for the story tree model: loading, validation, pool discovery."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.interactive_story.core import (DEFAULT_STORIES_DIR, MAX_OPTIONS,
                                         StoryError, discover_stories,
                                         load_stories, load_story)

VALID = """
[meta]
title = "Тест"
start = "a"

[nodes.a]
text = "Сцена А"
[[nodes.a.options]]
text = "В Б"
next = "b"
[[nodes.a.options]]
text = "Сразу в финал"
result = "Быстро же."
next = "end"

[nodes.b]
text = "Сцена Б"
[[nodes.b.options]]
text = "Назад в А"
next = "a"
[[nodes.b.options]]
text = "В финал"
next = "end"

[nodes.end]
text = "Финал"
ending = true
"""


def write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


class LoadValidTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_loads_valid_story(self):
        story = load_story(write(self.tmp, "demo.toml", VALID))
        self.assertEqual(story.name, "demo")
        self.assertEqual(story.title, "Тест")
        self.assertEqual(story.start, "a")
        self.assertEqual(len(story.scenes), 3)
        self.assertEqual(story.description, "")

    def test_cycle_is_allowed(self):  # a <-> b loop, ending still reachable
        story = load_story(write(self.tmp, "demo.toml", VALID))
        self.assertEqual(story.scene("b").options[0].next, "a")

    def test_option_result_parsed(self):
        story = load_story(write(self.tmp, "demo.toml", VALID))
        self.assertEqual(story.scene("a").options[1].result, "Быстро же.")
        self.assertIsNone(story.scene("a").options[0].result)

    def test_endings(self):
        story = load_story(write(self.tmp, "demo.toml", VALID))
        endings = story.endings()
        self.assertEqual([s.id for s in endings], ["end"])
        self.assertTrue(endings[0].ending)

    def test_real_pool_is_valid(self):
        stories = load_stories(DEFAULT_STORIES_DIR)
        self.assertGreaterEqual(len(stories), 2,
                                "ожидаются обе демо-истории в stories/")


class LoadInvalidTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def check(self, body: str, needle: str):
        with self.assertRaises(StoryError, msg=body) as cm:
            load_story(write(self.tmp, "bad.toml", body))
        self.assertIn(needle, str(cm.exception))

    def test_broken_toml(self):
        self.check("[meta\ntitle = ", "ошибка TOML")

    def test_missing_meta(self):
        self.check('[nodes.a]\ntext = "x"\nending = true\n', "[meta]")

    def test_missing_title(self):
        self.check('[meta]\nstart = "a"\n[nodes.a]\ntext = "x"\nending = true\n',
                   "meta.title")

    def test_missing_start(self):
        self.check('[meta]\ntitle = "T"\n[nodes.a]\ntext = "x"\nending = true\n',
                   "meta.start")

    def test_start_not_found(self):
        self.check('[meta]\ntitle = "T"\nstart = "zzz"\n'
                   '[nodes.a]\ntext = "x"\nending = true\n', "zzz")

    def test_option_next_not_found(self):
        self.check('[meta]\ntitle = "T"\nstart = "a"\n'
                   '[nodes.a]\ntext = "x"\n[[nodes.a.options]]\n'
                   'text = "o"\nnext = "zzz"\n', "zzz")

    def test_empty_scene_text(self):
        self.check('[meta]\ntitle = "T"\nstart = "a"\n'
                   '[nodes.a]\ntext = "  "\nending = true\n', "text")

    def test_no_options_no_ending(self):
        self.check('[meta]\ntitle = "T"\nstart = "a"\n'
                   '[nodes.a]\ntext = "x"\n', "опций")

    def test_too_many_options(self):
        opts = "\n".join(f'[[nodes.a.options]]\ntext = "o{i}"\nnext = "b"'
                         for i in range(MAX_OPTIONS + 1))
        self.check(f'[meta]\ntitle = "T"\nstart = "a"\n'
                   f'[nodes.a]\ntext = "x"\n{opts}\n'
                   f'[nodes.b]\ntext = "y"\nending = true\n', "1..9")

    def test_ending_with_options(self):
        self.check('[meta]\ntitle = "T"\nstart = "a"\n'
                   '[nodes.a]\ntext = "x"\nending = true\n'
                   '[[nodes.a.options]]\ntext = "o"\nnext = "a"\n',
                   "концовка")

    def test_no_reachable_ending(self):  # cycle without an exit
        self.check('[meta]\ntitle = "T"\nstart = "a"\n'
                   '[nodes.a]\ntext = "x"\n[[nodes.a.options]]\n'
                   'text = "o"\nnext = "b"\n'
                   '[nodes.b]\ntext = "y"\n[[nodes.b.options]]\n'
                   'text = "o"\nnext = "a"\n', "концовка")


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sorted_and_toml_only(self):
        write(self.tmp, "b.toml", VALID)
        write(self.tmp, "a.toml", VALID)
        write(self.tmp, "notes.txt", "не история")
        names = [p.name for p in discover_stories(self.tmp)]
        self.assertEqual(names, ["a.toml", "b.toml"])

    def test_missing_directory(self):
        self.assertEqual(discover_stories(self.tmp / "nope"), [])


if __name__ == "__main__":
    unittest.main()
