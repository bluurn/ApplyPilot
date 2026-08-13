"""Local HTTP server for live dashboard and apply-queue views."""

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
            body = b"<h1>404 Not Found</h1>"
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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
