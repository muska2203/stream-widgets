@echo off
rem Portable build of interactive_story: PyInstaller onedir -> ZIP.
rem Run from anywhere; operates in the repo root.
setlocal
cd /d "%~dp0\.."

py -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing pyinstaller...
    py -m pip install pyinstaller
)

py -m PyInstaller packaging\interactive_story.spec --noconfirm
if errorlevel 1 (
    echo BUILD FAILED
    exit /b 1
)

copy /y packaging\README_STREAMER.txt dist\InteractiveStory\ >nul
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\InteractiveStory' -DestinationPath 'dist\InteractiveStory-win64.zip'"
echo Done: dist\InteractiveStory-win64.zip
