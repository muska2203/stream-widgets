# PyInstaller spec: portable onedir build of interactive_story.
# Build from the repo root:
#   py -m PyInstaller packaging/interactive_story.spec --noconfirm
# Output: dist/InteractiveStory/ (see packaging/build_zip.bat).

import os

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.dirname(SPECPATH)  # repo root (spec lives in packaging/)


def p(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


datas = [
    (p("packaging", "defaults", "config.toml"), "defaults"),
    (p(".env.example"), "defaults"),
    (p("apps", "interactive_story", "stories"), "defaults/stories"),
    (p("apps", "interactive_story", "web"), "web"),  # страница оверлея
]
binaries = []
hiddenimports = collect_submodules("twitchio")

a = Analysis(
    [p("packaging", "run_interactive_story.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["test"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InteractiveStory",
    console=True,  # консоль оставляем: стримеру видны ошибки и лог
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="InteractiveStory",
)
