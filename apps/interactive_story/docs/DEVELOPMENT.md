# Интерактивная история — DEVELOPMENT

Контракты модулей, грабли, как развивать. Общие правила репо — в корневом
AGENTS.md (тесты `py -m unittest discover`, агент не запускает UI).

## Модули

- `core/story.py` — чистая модель (без IO): `Story/Scene/Option`,
  `load_story(path)`, `discover_stories(dir)`, `load_stories(dir)`,
  `StoryError`. Валидация дерева при загрузке — см. DESIGN.md.
- `core/choices.py` — `make_choice_validator(n) -> Validator`: цифры
  `1..n`, всё прочее → `ValueError`. Подключается к `streamkit.VoteLoop`
  через `validate=`.
- `core/__main__.py` — CLI-проверка пула: `py -m apps.interactive_story.core`.
- `config.py` — `@dataclass Config` + `load_config()` (streamkit
  `load_toml_config`; неизвестные ключи TOML игнорируются) +
  `default_config_path()` (frozen: config.toml рядом с exe).
- `narration.py` — точка расширения под озвучку: протокол `Narrator`
  (`say_scene/say_result/stop`) и `NullNarrator` (no-op дефолт).
- `webui.py` — `WebUI`: модель состояния оверлея (чистый Python, без
  сети). Тот же интерфейс, что был у ursina-UI: Game зовёт
  `set_header/show_select/show_move/show_options/update_votes/
  show_outcome/enter_sleep/show_ending`, WebUI складывает всё в
  JSON-сериализуемый dict и публикует атомарным свопом `_snapshot`.
  Формат — см. `tests/test_webui.py` и комментарии в файле.
- `server.py` — `OverlayServer(ui, port)`: stdlib `ThreadingHTTPServer`
  в daemon-потоке на 127.0.0.1. Отдаёт `web/overlay.html` (`/`) и
  `ui.snapshot` (`/state.json`); страница опрашивает состояние каждые
  200 мс. Путь к html: frozen — `streamkit.paths.bundled_dir()/web/`,
  dev — рядом с пакетом.
- `web/overlay.html` — самодостаточная страница оверлея (CSS+JS inline,
  шрифты Google Fonts с фолбэками). Вся верстка/стили/анимации — здесь;
  Python про пиксели ничего не знает.
- `setup_wizard.py` — первый запуск frozen-сборки: `ensure_user_files()`
  копирует дефолты (config.toml, .env.example, stories/) из бандла рядом с
  exe, `needs_setup()` решает, нужен ли мастер (канал/токен, tkinter);
  флаг `--setup` форсирует в dev. Чистые хелперы покрыты `tests/test_setup.py`.
- `game.py` — `Game`: автомат SELECT/VOTING/OUTCOME/SLEEP/END, единая
  точка входа чата `handle_chat_message(user, text)`. Чистый Python:
  главный цикл в `main.py` зовёт `game.update(dt)` ~60 раз в секунду.
- `main.py` — entry point: мастер → конфиг → `Game` + `OverlayServer` →
  цикл на `time.monotonic` (`--smoke` — авто-выход через 20 с).

## Игровой цикл — точные правила

- Весь тайминг через `dt` в `Game.update(dt)` (вызывается из цикла в
  `main.py`); никаких sleep/потоков в игровой логике.
- `VoteLoop` создаётся заново на каждую фазу голосования: у SELECT и у
  каждой сцены свой `validate` (число вариантов разное). Варианты
  открываются сразу вместе с текстом сцены, без задержки.
- Таймер хода единый: `Game.time_left = round_duration` тикает от показа
  сцены; голосование закрывается явным `vote_loop.finish()` при
  `time_left <= 0` (у VoteLoop в фазе VOTING `update(dt)` НЕ вызывается —
  его внутренний таймер не используется).
- `move_number` увеличивается только при применённом выборе; повтор раунда
  без голосов ход не засчитывает и сцену не меняет.
- После концовки игра возвращается в SELECT — цикл бесконечный, стриму не
  нужен рестарт. Пул историй перечитывается при каждом входе в SELECT.

## Оверлей (OBS Browser Source)

Окна нет: оверлей — страница `http://127.0.0.1:<overlay_port>` (печатается
при старте), стример добавляет её в OBS источником «Браузер». Прозрачность
нативная — хромакей не нужен. Страница опрашивает `/state.json` и
пересобирает DOM только при смене структуры состояния (иначе
перезапускались бы CSS-анимации при каждом опросе).

Фазы снапшота: `select` (список историй с голосами), `move` (сцена +
варианты; `show_outcome` только помечает вариант `chosen` и кладёт
`result`), `sleep` (сцена/варианты пусты, виден `result` — он был выставлен
ещё в `show_outcome`), `end` (концовка), `error` (пул историй битый/пуст).

## Озвучка (будущее)

`Game(cfg, narrator=...)` принимает любой объект с методами протокола
`Narrator`: `say_scene(text)` зовётся при показе текста хода,
`say_result(text)` — при показе последствий, `stop()` — при сне, концовке
и смене истории. Реальный TTS = свой класс + передача в `Game` (в `main.py`
или извне), игровой код не трогаем. В файлах историй можно заранее
добавлять свои ключи (напр. `voice = "..."`) — загрузчик их игнорирует.

## Грабли

- `WebUI._publish()` делает `deepcopy` и своп ссылки — так HTTP-потоки
  сервера читают `ui.snapshot` без локов. Мутировать `_state` мимо
  `_publish()` нельзя: страница не увидит изменений.
- `VoteLoop.update(dt)` может вызвать коллбэк, который меняет фазу и
  заменяет/обнуляет `game.vote_loop` (в т.ч. replay хода без голосов: фаза
  остаётся VOTING, но `vote_loop = None`) — после `update()` в
  `Game.update` обращаться к нему только под проверкой `self.state`
  **и** `self.vote_loop is not None`.
- Порт оверлея занят → `OverlayServer` падает с понятным сообщением;
  смена — `overlay_port` в config.toml (и адрес источника в OBS).
- Google Fonts требуют интернет (у стримера он есть); офлайн страница
  остаётся рабочей на фолбэк-шрифтах.
- Русские строки в консоли Windows могут печататься кракозябрами (cp866) —
  это только отображение консоли, не данные.
- В TOML запятая после значения (`text = "...",`) — синтаксическая ошибка;
  при ручном редактировании историй прогонять `py -m apps.interactive_story.core`.

## Portable-сборка (для стримеров)

`packaging/build_zip.bat` из корня репо → `dist/InteractiveStory-win64.zip`
(PyInstaller onedir, spec — `packaging/interactive_story.spec`). В frozen
-режиме `config.toml`, `.env` и `stories/` читаются рядом с exe; дефолты
лежат в бандле (`sys._MEIPASS/defaults`) и копируются наружу первым запуском.
Страница оверлея (`web/`) — read-only ресурс бандла, путь через
`streamkit.paths.bundled_dir()`. Правило: новые пользовательские файлы
резолвить через `streamkit.paths`, не через `__file__` напрямую.
Запуск exe проверяет пользователь.

## Верификация

- Агент: `py -m unittest discover` (все тесты репо), `py -m
  apps.interactive_story.core` (пул валиден), compileall/импорты.
- Пользователь: `py -m apps.interactive_story` (mock_chat=false — живой
  чат; true — эмуляция) → открыть напечатанный адрес в браузере, прогнать
  все состояния; затем источник «Браузер» в OBS.
