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
log = logging.getLogger(__name__)


# --- single-job enqueue ---

def _run_enqueue_thread(url: str) -> None:
    """Re-generate tailored resume + cover letter for one job and add it to the queue."""
    import re
    from applypilot.config import COVER_LETTER_DIR, RESUME_PATH, TAILORED_DIR, load_profile
    from applypilot.database import get_connection
    from applypilot.scoring.cover_letter import generate_cover_letter
    from applypilot.scoring.tailor import tailor_resume

    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if not row:
        log.error("Enqueue: job not found: %s", url[:80])
        return
    job = dict(row)

    profile = load_profile()
    resume_text = RESUME_PATH.read_text(encoding="utf-8")

    personal = profile.get("personal", {})
    full_name = personal.get("full_name") or personal.get("preferred_name", "")
    name_slug = re.sub(r"\s+", "_", full_name).strip() if full_name else "CV"
    safe_title = re.sub(r"[^\w\s-]", "", job["title"])[:50].strip().replace(" ", "_")
    safe_site  = re.sub(r"[^\w\s-]", "", job["site"])[:20].strip().replace(" ", "_")
    now = datetime.now(timezone.utc).isoformat()

    # --- tailor resume ---
    try:
        tailored, report = tailor_resume(resume_text, job, profile)
        sub = TAILORED_DIR / f"{safe_site}_{safe_title}"
        sub.mkdir(parents=True, exist_ok=True)
        txt_path = sub / f"{name_slug}_CV.txt"
        txt_path.write_text(tailored, encoding="utf-8")
        job_desc = (
            f"Title: {job['title']}\nCompany: {job['site']}\n"
            f"URL: {job['url']}\n\n{job.get('full_description', '')}"
        )
        (sub / "_JOB.txt").write_text(job_desc, encoding="utf-8")
        (sub / "_REPORT.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        pdf_path = None
        if report.get("status") == "approved":
            try:
                from applypilot.scoring.pdf import convert_to_pdf
                pdf_path = str(convert_to_pdf(txt_path))
            except Exception:
                pass
        conn.execute(
            "UPDATE jobs SET tailored_resume_path=?, tailored_at=?, "
            "tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
            (str(txt_path), now, url),
        )
        conn.commit()
        job = dict(conn.execute("SELECT * FROM jobs WHERE url=?", (url,)).fetchone())
        log.info("Enqueue tailor done: %s", job["title"][:60])
    except Exception as exc:
        log.error("Enqueue tailor failed for %s: %s", url[:80], exc)
        return

    # --- cover letter ---
    try:
        letter = generate_cover_letter(resume_text, job, profile)
        sub = COVER_LETTER_DIR / f"{safe_site}_{safe_title}"
        sub.mkdir(parents=True, exist_ok=True)
        cl_path = sub / f"{name_slug}_Cover_Letter.txt"
        cl_path.write_text(letter, encoding="utf-8")
        try:
            from applypilot.scoring.pdf import convert_to_pdf
            convert_to_pdf(cl_path)
        except Exception:
            pass
        conn.execute(
            "UPDATE jobs SET cover_letter_path=?, cover_letter_at=?, "
            "cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
            (str(cl_path), now, url),
        )
        log.info("Enqueue cover letter done: %s", job["title"][:60])
    except Exception as exc:
        log.error("Enqueue cover letter failed for %s: %s", url[:80], exc)

    # clear enqueuing/skip so the job enters the queue
    conn.execute(
        "UPDATE jobs SET apply_status=NULL WHERE url=?", (url,)
    )
    conn.commit()
    console.print(f"[green]Enqueued:[/green] {job['title'][:60]}")


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
        elif path == "/job/enqueue":
            self._handle_job_enqueue(data)
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

    def _handle_job_enqueue(self, data: dict) -> None:
        url = data.get("url", "")
        if not url:
            self._respond(400, b'{"ok":false,"error":"missing url"}', "application/json")
            return
        from applypilot.database import get_connection
        conn = get_connection()
        conn.execute("UPDATE jobs SET apply_status='enqueuing' WHERE url=?", (url,))
        conn.commit()
        thread = threading.Thread(target=_run_enqueue_thread, args=(url,), daemon=True)
        thread.start()
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
        from applypilot.database import get_stats
        body = json.dumps({
            "running": running,
            "stopped": stopped,
            "new_logs": new_logs,
            "result": result,
            "finished_at": finished_at,
            "stats": get_stats(),
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
