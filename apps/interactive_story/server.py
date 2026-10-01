"""Local HTTP server for the web overlay (OBS Browser Source).

Serves the self-contained overlay page and the current game state as JSON;
the page polls `/state.json` a few times per second. Stdlib only, bound to
localhost. The server thread is a daemon: the game loop in `main.py` owns
the process lifetime.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from streamkit.paths import bundled_dir

from apps.interactive_story.webui import WebUI

DEFAULT_PORT = 8765


def _overlay_html_path() -> Path:
    bundled = bundled_dir()
    if bundled is not None:  # frozen: web/ лежит в бандле рядом с defaults/
        return bundled / "web" / "overlay.html"
    return Path(__file__).resolve().parent / "web" / "overlay.html"


class OverlayServer:
    def __init__(self, ui: WebUI, port: int = DEFAULT_PORT,
                 host: str = "127.0.0.1"):
        html = _overlay_html_path().read_bytes()
        snapshot_json = lambda: json.dumps(  # noqa: E731
            ui.snapshot, ensure_ascii=False).encode("utf-8")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (stdlib naming)
                if self.path in ("/", "/overlay.html"):
                    self._respond(200, "text/html; charset=utf-8", html)
                elif self.path == "/state.json":
                    self._respond(200, "application/json; charset=utf-8",
                                  snapshot_json())
                else:
                    self._respond(404, "text/plain; charset=utf-8",
                                  b"not found")

            def _respond(self, code: int, content_type: str,
                         body: bytes) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:  # тишина в консоли игры
                pass

        try:
            self._httpd = ThreadingHTTPServer((host, port), Handler)
        except OSError as e:
            raise RuntimeError(
                f"Не удалось открыть порт {port} для оверлея ({e}). "
                f"Порт занят? Смени overlay_port в config.toml.") from e
        self.host, self.port = self._httpd.server_address[:2]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
