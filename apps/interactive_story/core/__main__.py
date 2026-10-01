"""CLI check of the story pool: py -m apps.interactive_story.core [dir]"""

from __future__ import annotations

import sys
from pathlib import Path

from apps.interactive_story.core.story import (DEFAULT_STORIES_DIR, StoryError,
                                               discover_stories, load_story)


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_STORIES_DIR
    paths = discover_stories(directory)
    if not paths:
        print(f"нет историй в {directory}", flush=True)
        sys.exit(1)
    failed = 0
    for path in paths:
        try:
            story = load_story(path)
        except StoryError as e:
            failed += 1
            print(f"FAIL {path.name}: {e}", flush=True)
            continue
        print(f"OK   {story.name}: «{story.title}» — сцен: {len(story.scenes)}, "
              f"концовок: {len(story.endings())}", flush=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
