"""Local HTTP server for live dashboard and apply-queue views."""

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from rich.console import Console

console = Console()

_ROUTES = {
    "/": "dashboard",
    "/dashboard": "dashboard",
    "/queue": "queue",
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        route = _ROUTES.get(self.path.split("?")[0])
        if route == "dashboard":
            from applypilot.view import render_dashboard
            body = render_dashboard().encode()
        elif route == "queue":
            from applypilot.apply_queue import render_queue
            body = render_queue().encode()
        else:
            self._respond(404, b"<h1>404 Not Found</h1>", "text/html; charset=utf-8")
            return
        self._respond(200, body, "text/html; charset=utf-8")

    def do_POST(self):
        if self.path.split("?")[0] != "/action":
            self._respond(404, b'{"ok":false}', "application/json")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._respond(400, b'{"ok":false,"error":"bad json"}', "application/json")
            return
        url = data.get("url", "")
        action = data.get("action", "")
        if not url or action not in ("applied", "dismissed"):
            self._respond(400, b'{"ok":false,"error":"bad request"}', "application/json")
            return
        from applypilot.apply.launcher import mark_job
        status = "applied" if action == "applied" else "skip"
        mark_job(url, status)
        color = "green" if action == "applied" else "dim"
        console.print(f"[{color}]{action}: {url[:80]}[/{color}]")
        self._respond(200, b'{"ok":true}', "application/json")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 7777, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), _Handler)
    url = f"http://{host}:{port}"
    console.print(f"[green]Serving on {url}[/green]")
    console.print("  /            -> dashboard")
    console.print("  /queue       -> apply queue")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    if open_browser:
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        subprocess.Popen(["xdg-open", url], env=env)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")
