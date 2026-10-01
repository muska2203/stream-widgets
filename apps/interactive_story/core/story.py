"""Story tree model: TOML loading and validation (see docs/DESIGN.md).

A story is a tree (directed graph, cycles allowed) of scenes. Each scene
shows text; non-ending scenes offer 1..9 options the chat votes on by digit.
An option may carry a `result` text (consequences shown after the vote) and
always points to the next scene. Scenes with `ending = true` end the story.

One story = one file `stories/<name>.toml`; adding/removing a file is all
it takes to change the pool.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

MAX_OPTIONS = 9  # варианты голосуются цифрами 1..9

DEFAULT_STORIES_DIR = Path(__file__).resolve().parent.parent / "stories"


def default_stories_dir() -> Path:
    """Pool directory: next to the exe in frozen builds, else the bundled one."""
    from streamkit.paths import frozen_app_dir
    frozen = frozen_app_dir()
    return (frozen / "stories") if frozen else DEFAULT_STORIES_DIR


class StoryError(ValueError):
    """Invalid story file (bad structure, broken links, no reachable ending)."""


@dataclass
class Option:
    text: str
    next: str  # id следующей сцены
    result: str | None = None  # последствия, показываются после выбора


@dataclass
class Scene:
    id: str
    text: str
    options: list[Option] = field(default_factory=list)
    ending: bool = False
    ending_label: str | None = None


@dataclass
class Story:
    name: str  # имя файла без .toml
    title: str
    description: str
    start: str
    scenes: dict[str, Scene]

    def scene(self, scene_id: str) -> Scene:
        return self.scenes[scene_id]

    def endings(self) -> list[Scene]:
        return [s for s in self.scenes.values() if s.ending]


def load_story(path: str | Path) -> Story:
    """Parse and validate one story file; raises StoryError on any problem."""
    path = Path(path)
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise StoryError(f"{path.name}: ошибка TOML: {e}") from e
    except OSError as e:
        raise StoryError(f"{path.name}: не читается: {e}") from e

    meta = data.get("meta")
    if not isinstance(meta, dict):
        raise StoryError(f"{path.name}: нет секции [meta]")
    title = meta.get("title")
    if not isinstance(title, str) or not title.strip():
        raise StoryError(f"{path.name}: meta.title обязателен и не пуст")
    start = meta.get("start")
    if not isinstance(start, str) or not start:
        raise StoryError(f"{path.name}: meta.start обязателен")
    description = meta.get("description", "")
    if not isinstance(description, str):
        raise StoryError(f"{path.name}: meta.description должен быть строкой")

    nodes = data.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise StoryError(f"{path.name}: нет ни одной сцены [nodes.<id>]")

    scenes: dict[str, Scene] = {}
    for scene_id, node in nodes.items():
        scenes[scene_id] = _parse_scene(path.name, scene_id, node)

    if start not in scenes:
        raise StoryError(f"{path.name}: meta.start указывает на несуществующую "
                         f"сцену {start!r}")
    for scene in scenes.values():
        for opt in scene.options:
            if opt.next not in scenes:
                raise StoryError(f"{path.name}: сцена {scene.id!r}: опция "
                                 f"{opt.text!r} ведёт на несуществующую сцену "
                                 f"{opt.next!r}")
    _require_reachable_ending(path.name, scenes, start)

    return Story(name=path.stem, title=title.strip(),
                 description=description.strip(), start=start, scenes=scenes)


def _parse_scene(file: str, scene_id: str, node: object) -> Scene:
    if not isinstance(node, dict):
        raise StoryError(f"{file}: сцена {scene_id!r} должна быть таблицей")
    text = node.get("text")
    if not isinstance(text, str) or not text.strip():
        raise StoryError(f"{file}: сцена {scene_id!r}: пустой text")
    ending = bool(node.get("ending", False))
    ending_label = node.get("ending_label")
    if ending_label is not None and not isinstance(ending_label, str):
        raise StoryError(f"{file}: сцена {scene_id!r}: ending_label — строка")

    raw_options = node.get("options", [])
    if not isinstance(raw_options, list):
        raise StoryError(f"{file}: сцена {scene_id!r}: options — список")
    options = [_parse_option(file, scene_id, o) for o in raw_options]

    if ending:
        if options:
            raise StoryError(f"{file}: сцена {scene_id!r}: концовка не может "
                             f"иметь options")
    elif not 1 <= len(options) <= MAX_OPTIONS:
        raise StoryError(f"{file}: сцена {scene_id!r}: должно быть "
                         f"1..{MAX_OPTIONS} опций или ending = true, "
                         f"а тут {len(options)}")
    return Scene(id=scene_id, text=text.strip(), options=options,
                 ending=ending, ending_label=ending_label)


def _parse_option(file: str, scene_id: str, raw: object) -> Option:
    if not isinstance(raw, dict):
        raise StoryError(f"{file}: сцена {scene_id!r}: опция должна быть "
                         f"таблицей")
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        raise StoryError(f"{file}: сцена {scene_id!r}: опция с пустым text")
    next_ = raw.get("next")
    if not isinstance(next_, str) or not next_:
        raise StoryError(f"{file}: сцена {scene_id!r}: опция {text!r} без next")
    result = raw.get("result")
    if result is not None and not isinstance(result, str):
        raise StoryError(f"{file}: сцена {scene_id!r}: result — строка")
    return Option(text=text.strip(), next=next_, result=result)


def _require_reachable_ending(file: str, scenes: dict[str, Scene],
                              start: str) -> None:
    """At least one ending must be reachable from the start scene.

    Plain reachability (not "all paths terminate"): finite graph + reachable
    ending means a simple path to it exists; story cycles are allowed.
    """
    seen: set[str] = set()
    stack = [start]
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        stack.extend(o.next for o in scenes[sid].options)
    if not any(scenes[sid].ending for sid in seen):
        raise StoryError(f"{file}: из стартовой сцены {start!r} недостижима "
                         f"ни одна концовка")


def discover_stories(directory: str | Path | None = None) -> list[Path]:
    """Sorted list of story files (*.toml) in the pool directory."""
    directory = (Path(directory) if directory is not None
                 else default_stories_dir())
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.suffix == ".toml")


def load_stories(directory: str | Path | None = None) -> list[Story]:
    """Load the whole pool; StoryError names the broken file."""
    return [load_story(p) for p in discover_stories(directory)]
