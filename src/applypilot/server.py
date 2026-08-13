"""Local HTTP server for live dashboard and apply-queue views."""

import json
import logging
import os
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from rich.console import Console

console = Console()

# --- pipeline run state ---

_pipeline_state: dict = {
    "running": False,
    "stopped": False,
    "logs": [],
    "result": None,
    "started_at": None,
    "finished_at": None,
}
_pipeline_lock = threading.Lock()


class _LogCapture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        with _pipeline_lock:
            _pipeline_state["logs"].append(msg)


def _run_pipeline_thread(params: dict) -> None:
    from applypilot import cancel
    cancel.clear()
    handler = _LogCapture()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S"))
    logger = logging.getLogger("applypilot")
    logger.addHandler(handler)
    try:
        from applypilot.pipeline import run_pipeline
        result = run_pipeline(**params)
        with _pipeline_lock:
            _pipeline_state["result"] = result
            _pipeline_state["stopped"] = cancel.is_set()
            _pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        with _pipeline_lock:
            _pipeline_state["result"] = {"stages": [], "errors": {"run": str(exc)}, "elapsed": 0}
            _pipeline_state["stopped"] = False
            _pipeline_state["finished_at"] = datetime.now(timezone.utc).isoformat()
    finally:
        logger.removeHandler(handler)
        with _pipeline_lock:
            _pipeline_state["running"] = False


# --- HTTP handler ---

_GET_ROUTES = {
    "/": "dashboard",
    "/dashboard": "dashboard",
    "/queue": "queue",
    "/pipeline": "pipeline",
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/pipeline/state":
            self._handle_pipeline_state(qs)
            return

        route = _GET_ROUTES.get(path)
        if route == "dashboard":
            from applypilot.view import render_dashboard
            body = render_dashboard().encode()
        elif route == "queue":
            from applypilot.apply_queue import render_queue
            body = render_queue().encode()
        elif route == "pipeline":
            from applypilot.database import get_stats
            from applypilot.pipeline_view import render_pipeline
            with _pipeline_lock:
                state_snap = {
                    "running": _pipeline_state["running"],
                    "logs": list(_pipeline_state["logs"]),
                    "result": _pipeline_state["result"],
                    "started_at": _pipeline_state["started_at"],
                    "finished_at": _pipeline_state["finished_at"],
                }
            body = render_pipeline(state_snap, get_stats()).encode()
        else:
            self._respond(404, b"<h1>404 Not Found</h1>", "text/html; charset=utf-8")
            return
        self._respond(200, body, "text/html; charset=utf-8")

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._respond(400, b'{"ok":false,"error":"bad json"}', "application/json")
            return

        if path == "/action":
            self._handle_action(data)
        elif path == "/pipeline/run":
            self._handle_pipeline_run(data)
        elif path == "/pipeline/stop":
            self._handle_pipeline_stop()
        else:
            self._respond(404, b'{"ok":false}', "application/json")

    def _handle_action(self, data: dict) -> None:
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

    def _handle_pipeline_stop(self) -> None:
        from applypilot import cancel
        cancel.request()
        console.print("[yellow]Pipeline stop requested[/yellow]")
        self._respond(200, b'{"ok":true}', "application/json")

    def _handle_pipeline_run(self, data: dict) -> None:
        with _pipeline_lock:
            if _pipeline_state["running"]:
                self._respond(
                    200,
                    json.dumps({"ok": False, "error": "already running"}).encode(),
                    "application/json",
                )
                return
            _pipeline_state["running"] = True
            _pipeline_state["stopped"] = False
            _pipeline_state["logs"] = []
            _pipeline_state["result"] = None
            _pipeline_state["started_at"] = datetime.now(timezone.utc).isoformat()
            _pipeline_state["finished_at"] = None

        stages_raw = data.get("stages", ["all"])
        params = {
            "stages": stages_raw if isinstance(stages_raw, list) else ["all"],
            "min_score": int(data.get("min_score", 7)),
            "workers": int(data.get("workers", 4)),
            "tailor_limit": int(data.get("tailor_limit", 20)) or None,
            "validation_mode": data.get("validation", "normal"),
        }
        thread = threading.Thread(target=_run_pipeline_thread, args=(params,), daemon=True)
        thread.start()
        console.print(f"[blue]Pipeline started:[/blue] stages={params['stages']}")
        self._respond(200, b'{"ok":true}', "application/json")

    def _handle_pipeline_state(self, qs: dict) -> None:
        try:
            offset = int(qs.get("offset", ["0"])[0])
        except (ValueError, IndexError):
            offset = 0
        with _pipeline_lock:
            new_logs = list(_pipeline_state["logs"][offset:])
            running = _pipeline_state["running"]
            stopped = _pipeline_state["stopped"]
            result = _pipeline_state["result"]
            finished_at = _pipeline_state["finished_at"]
        body = json.dumps({
            "running": running,
            "stopped": stopped,
            "new_logs": new_logs,
            "result": result,
            "finished_at": finished_at,
        }).encode()
        self._respond(200, body, "application/json")

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
    console.print("  /pipeline    -> pipeline control")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    if open_browser:
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        subprocess.Popen(["xdg-open", url], env=env)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")
