# StreamWidgets — библиотека streamkit + мини-приложения для Twitch

Монорепо интерактивных стрим-приложений:

- **`streamkit/`** — переиспользуемая библиотека (pip-пакет, `pyproject.toml`):
  чат Twitch и мок-чат, голосование с таймером раундов, окно-оверлей для OBS
  (хромакей, borderless), загрузка конфига и `.env`.
- **`apps/<name>/`** — отдельные приложения на этой библиотеке. Сейчас:
  - **`apps/rubiks_cube/`** — чат коллективно собирает кубик Рубика, голосуя
    командами (`u1`, `r2`, `wu`...) за каждый ход.
  - **`apps/interactive_story/`** — чат коллективно проходит древовидную
    историю, голосуя цифрами (`1`..`9`) за варианты действий; истории —
    TOML-файлы в `stories/`, между ходами игра «засыпает» и прячет UI.
  - **`apps/mini_rpg/`** — чат ведёт героя через бесконечный забег:
    выбирает двери-события (мобы, магазин, зона отдыха), дерётся с мобами
    (блоки по направлениям), качает статы и покупает снаряжение. Оверлей —
    веб-страница для OBS Browser Source с прозрачной рамкой аватарки под
    камеру стримера.

Стек: Python 3.11+ · TwitchIO (чат) · Ursina (окно кубика) ·
OBS Browser Source (веб-оверлей истории и мини-RPG, без хромакея).

Документация кубика: [apps/rubiks_cube/docs/DESIGN.md](apps/rubiks_cube/docs/DESIGN.md) ·
[DEVELOPMENT.md](apps/rubiks_cube/docs/DEVELOPMENT.md) (контракты, грабли, статус).
Документация истории: [apps/interactive_story/docs/DESIGN.md](apps/interactive_story/docs/DESIGN.md) ·
[DEVELOPMENT.md](apps/interactive_story/docs/DEVELOPMENT.md).
Документация мини-RPG: [apps/mini_rpg/docs/DESIGN.md](apps/mini_rpg/docs/DESIGN.md) ·
[DEVELOPMENT.md](apps/mini_rpg/docs/DEVELOPMENT.md) (контракты, грабли, статус) ·
[PLAN.md](apps/mini_rpg/docs/PLAN.md) (план реализации с отметками прогресса).

## Быстрый старт (Windows)

Интерпретатор вызывается через `py` (Python 3.14; `python` в PATH — заглушка
Windows Store). Все команды — из корня репо.

```bash
py -m pip install -r requirements.txt

# все юнит-тесты (библиотека + приложения)
py -m unittest discover

# игра «кубик Рубика»: безрамочное окно, хромакей-фон
py -m apps.rubiks_cube

# CLI-проверка модели куба: py -m apps.rubiks_cube.core [ходов] [seed]
py -m apps.rubiks_cube.core 10 42

# игра «интерактивная история»: выбор истории и ходов голосованием цифрами
# (при старте печатает адрес веб-оверлея для OBS Browser Source)
py -m apps.interactive_story

# проверка пула историй (stories/*.toml)
py -m apps.interactive_story.core

# игра «мини-RPG»: чат голосует за двери-события, бой и прокачку
# (при старте печатает адрес веб-оверлея для OBS Browser Source)
py -m apps.mini_rpg

# то же с эмуляцией чата / авто-выход через 20 с (smoke, всегда мок-чат)
py -m apps.mini_rpg --mock
py -m apps.mini_rpg --smoke

# проверка пулов мобов и предметов (mobs/*.toml, items/*.toml)
py -m apps.mini_rpg.core

# offscreen-проверка рендера: скриншоты в apps/rubiks_cube/tools/shots/
py apps/rubiks_cube/tools/render_check.py
```

Живой режим Twitch: положи токен в `.env` (см. `.env.example`), поставь
`mock_chat = false` в `config.toml` приложения, затем запусти его
(`py -m apps.rubiks_cube`, `py -m apps.interactive_story` или
`py -m apps.mini_rpg`).

## Сборка portable-версии для стримеров

`packaging/` — упаковка `interactive_story` в автономный Windows-бандл
(Python не нужен): PyInstaller onedir → ZIP. В frozen-сборке пользовательские
файлы (`config.toml`, `.env`, `stories/`) живут рядом с exe и при первом
запуске копируются из встроенных дефолтов; незаполненные канал/токен
запрашивает мастер настройки (tkinter). Пути переключает
`streamkit/paths.py` (`frozen_app_dir`/`bundled_defaults_dir`/`bundled_dir`).

```bash
packaging\build_zip.bat   # -> dist/InteractiveStory-win64.zip
```

Стримеру отдаётся ZIP; инструкция для него — `packaging/README_STREAMER.txt`
(копируется в бандл при сборке).

## Использование streamkit в своём приложении

```bash
py -m pip install -e <путь-к-этому-репо>[all]   # extras: twitch, ursina, all
```

```python
from streamkit import MockChat, TwitchChat, VoteLoop, VotingRound
from streamkit.overlay import WindowManipulator, create_overlay
```

Новое приложение — новая директория `apps/<name>/` со своими `core/` (чистая
логика), `tests/`, `tools/`, `docs/`, `config.toml` по образцу `rubiks_cube`.

## Структура

- `streamkit/` — библиотека: `chat.py`, `voting.py`, `config.py`, `paths.py`
  (frozen/dev-пути), `overlay/`, тесты в `streamkit/tests/`
- `apps/rubiks_cube/` — игра: `main.py`, `game.py` (автомат состояний),
  `cube_view.py` (3D-куб), `ui.py` (таймер, таблица голосов, победа),
  `core/` (модель куба), `tests/`, `tools/` (offscreen-проверки), `docs/`,
  `config.toml`
- `apps/interactive_story/` — игра (консольная, без окна): `main.py`,
  `game.py` (автомат SELECT/VOTING/OUTCOME/SLEEP/END), `webui.py` (модель
  состояния оверлея), `server.py` (HTTP для OBS Browser Source),
  `web/overlay.html` (страница оверлея), `setup_wizard.py` (мастер первого
  запуска в frozen-сборке), `narration.py` (задел под озвучку), `core/`
  (дерево историй из TOML, валидатор цифр), `stories/` (пул историй),
  `tests/`, `docs/`, `config.toml`
- `apps/mini_rpg/` — мини-RPG (консольная, без окна): `main.py` (entry
  point, цикл на monotonic), `game.py` (автомат RUN_START/EVENT/COMBAT/
  SHOP/REST/LEVELUP/GAME_OVER), `webui.py` (модель состояния оверлея),
  `server.py` (HTTP для OBS Browser Source), `web/overlay.html` (страница
  оверлея), `core/` (пулы контента из TOML, модель героя, бой с блоками,
  валидаторы команд), `mobs/` и `items/` (пулы контента), `tests/`,
  `docs/`, `config.toml`
- `packaging/` — PyInstaller-сборка interactive_story в portable ZIP:
  `interactive_story.spec`, `build_zip.bat`, `defaults/` (дистрибутивный
  config.toml), `README_STREAMER.txt`
