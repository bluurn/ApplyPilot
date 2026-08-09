"""Generate a static HTML apply queue page for manual job applications."""

import subprocess
from pathlib import Path

from rich.console import Console

from applypilot import config
from applypilot.database import get_connection

console = Console()


def _ats_label(url: str | None) -> str:
    if not url:
        return "Unknown"
    u = (url or "").lower()
    if "greenhouse.io" in u:
        return "Greenhouse"
    if "ashbyhq.com" in u:
        return "Ashby"
    if "workday" in u or "myworkdayjobs" in u:
        return "Workday"
    if "lever.co" in u:
        return "Lever"
    if "linkedin.com" in u:
        return "LinkedIn"
    if "indeed.com" in u:
        return "Indeed"
    return "Direct"


def _clean_url(job: dict) -> str:
    """Return the best URL to open for applying — prefer application_url but strip redirects and relative URLs."""
    app_url = job.get("application_url") or ""
    job_url = job.get("url") or ""
    if not app_url.startswith("http"):
        return job_url
    if "linkedin.com/signup" in app_url or "linkedin.com/authwall" in app_url:
        return job_url
    return app_url or job_url


def _read_text(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    # Cover letters stored as _CL.txt
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def _pdf_path(tailored_path: str | None) -> str:
    if not tailored_path:
        return ""
    return str(Path(tailored_path).with_suffix(".pdf"))


def _score_color(score: int) -> str:
    if score >= 9:
        return "#22c55e"
    if score >= 8:
        return "#3b82f6"
    return "#f59e0b"


def build_html(ready: list[dict], manual: list[dict]) -> str:
    def job_card(job: dict, tag: str = "") -> str:
        url = _clean_url(job)
        label = _ats_label(url)
        score = job.get("fit_score") or 0
        color = _score_color(score)
        cl_text = _read_text(job.get("cover_letter_path"))
        pdf = _pdf_path(job.get("tailored_resume_path"))
        cl_pdf = _pdf_path(job.get("cover_letter_path"))
        mark_cmd = f"python -m applypilot apply --mark-applied '{url}'"
        dismiss_cmd = f"python -m applypilot apply --dismiss '{url}'"
        card_id = f"card-{abs(hash(url)) % 100000}"
        tag_html = f'<span class="tag">{tag}</span>' if tag else ""

        cl_section = ""
        if cl_text:
            cl_section = f"""
            <div class="section-label">Cover Letter <button class="copy-btn" onclick="copyText(this)">Copy</button></div>
            <textarea class="cl-box" readonly>{cl_text}</textarea>"""

        return f"""
        <div class="card" id="{card_id}">
          <div class="card-header">
            <div class="score-badge" style="background:{color}">{score}/10</div>
            <div class="job-info">
              <div class="job-title">{job.get("title", "").strip()}</div>
              <div class="company">{job.get("company", "")} &mdash; <span class="location">{job.get("location", "")}</span></div>
            </div>
            <div class="ats-label">{label}</div>
            {tag_html}
            <button class="btn-x" title="Dismiss — copies command to clipboard" onclick="dismissCard('{card_id}', this, `{dismiss_cmd}`)">✕</button>
          </div>
          <div class="card-body">
            <div class="actions">
              <a class="btn btn-apply" href="{url}" target="_blank">Open Application ↗</a>
              <a class="btn btn-pdf" href="file://{pdf}" target="_blank">Resume PDF ↗</a>
              <a class="btn btn-pdf" href="file://{cl_pdf}" target="_blank">Cover Letter PDF ↗</a>
            </div>
            {cl_section}
            <div class="section-label">Resume PDF path: <button class="copy-btn" onclick="copyCmd(this, `{pdf}`)">Copy</button></div>
            <div class="cmd-box">{pdf}</div>
            <div class="section-label" style="margin-top:0.6rem">Cover Letter PDF path: <button class="copy-btn" onclick="copyCmd(this, `{cl_pdf}`)">Copy</button></div>
            <div class="cmd-box">{cl_pdf}</div>
            <div class="section-label" style="margin-top:0.6rem">After applying, mark done: <button class="copy-btn" onclick="copyCmd(this, `{mark_cmd}`)">Copy</button></div>
            <div class="cmd-box">{mark_cmd}</div>
            <div class="section-label" style="margin-top:0.6rem">Not a fit? Dismiss: <button class="copy-btn" onclick="copyCmd(this, `{dismiss_cmd}`)">Copy</button></div>
            <div class="cmd-box" style="color:#f87171">{dismiss_cmd}</div>
          </div>
        </div>"""

    ready_cards = "\n".join(job_card(dict(j)) for j in ready)
    manual_cards = "\n".join(job_card(dict(j), tag="Email verify") for j in manual)
    total = len(ready) + len(manual)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ApplyPilot — Apply Queue</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 2rem; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem; }}
  .subtitle {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 2rem; }}
  h2 {{ font-size: 1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.08em; margin: 2rem 0 1rem; }}
  .card {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; margin-bottom: 1.25rem; overflow: hidden; transition: border-color 0.2s; }}
  .card:hover {{ border-color: #475569; }}
  .card.done {{ opacity: 0.45; }}
  .card-header {{ display: flex; align-items: flex-start; gap: 1rem; padding: 1.1rem 1.25rem 0.9rem; }}
  .score-badge {{ font-size: 0.85rem; font-weight: 700; color: #fff; padding: 0.3rem 0.6rem; border-radius: 6px; white-space: nowrap; flex-shrink: 0; }}
  .job-info {{ flex: 1; min-width: 0; }}
  .job-title {{ font-size: 1rem; font-weight: 600; color: #f1f5f9; line-height: 1.3; }}
  .company {{ font-size: 0.85rem; color: #94a3b8; margin-top: 0.2rem; }}
  .location {{ color: #64748b; }}
  .ats-label {{ font-size: 0.75rem; background: #0f172a; border: 1px solid #334155; color: #94a3b8; padding: 0.2rem 0.5rem; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }}
  .tag {{ font-size: 0.72rem; background: #7c3aed22; border: 1px solid #7c3aed55; color: #a78bfa; padding: 0.2rem 0.5rem; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }}
  .card-body {{ padding: 0 1.25rem 1.1rem; }}
  .actions {{ display: flex; gap: 0.6rem; margin-bottom: 1rem; flex-wrap: wrap; }}
  .btn {{ display: inline-block; padding: 0.45rem 1rem; border-radius: 6px; font-size: 0.85rem; font-weight: 500; text-decoration: none; cursor: pointer; }}
  .btn-apply {{ background: #3b82f6; color: #fff; }}
  .btn-apply:hover {{ background: #2563eb; }}
  .btn-pdf {{ background: #1e3a5f; color: #93c5fd; border: 1px solid #2563eb44; }}
  .btn-pdf:hover {{ background: #1e40af22; }}
  .section-label {{ font-size: 0.75rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.4rem; display: flex; align-items: center; gap: 0.5rem; }}
  .cl-box {{ width: 100%; height: 220px; background: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #cbd5e1; font-size: 0.8rem; line-height: 1.5; padding: 0.75rem; resize: vertical; margin-bottom: 0.9rem; font-family: inherit; }}
  .copy-btn {{ font-size: 0.7rem; background: #334155; color: #94a3b8; border: none; padding: 0.15rem 0.5rem; border-radius: 4px; cursor: pointer; }}
  .copy-btn:hover {{ background: #475569; color: #e2e8f0; }}
  .copy-btn.copied {{ background: #166534; color: #86efac; }}
  .cmd-box {{ font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 0.78rem; background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 0.6rem 0.75rem; color: #7dd3fc; word-break: break-all; }}
  .progress {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 2rem; display: flex; gap: 2rem; }}
  .stat {{ text-align: center; }}
  .stat-num {{ font-size: 1.5rem; font-weight: 700; color: #f8fafc; }}
  .stat-lbl {{ font-size: 0.75rem; color: #64748b; margin-top: 0.15rem; }}
  .btn-x {{ background: none; border: none; color: #475569; font-size: 1rem; cursor: pointer; padding: 0.1rem 0.3rem; border-radius: 4px; flex-shrink: 0; line-height: 1; }}
  .btn-x:hover {{ color: #f87171; background: #1e1e2e; }}
</style>
</head>
<body>
<h1>ApplyPilot — Apply Queue</h1>
<p class="subtitle">{total} jobs ready for manual application · sorted by fit score</p>

<div class="progress">
  <div class="stat"><div class="stat-num" id="cnt-ready">{len(ready)}</div><div class="stat-lbl">To apply</div></div>
  <div class="stat"><div class="stat-num" id="cnt-manual">{len(manual)}</div><div class="stat-lbl">Email verify (Grafana Labs)</div></div>
  <div class="stat"><div class="stat-num" id="cnt-done">0</div><div class="stat-lbl">Done this session</div></div>
</div>

<h2>Ready to Apply</h2>
{ready_cards}

<h2>Grafana Labs — Email Verification Required</h2>
<p style="color:#94a3b8;font-size:0.85rem;margin-bottom:1rem;">
  These forms submit successfully but require entering an 8-character code from a Greenhouse email.
  Open the application, complete the form, then check <strong>bluurn@gmail.com</strong> for the code.
</p>
{manual_cards}

<script>
function copyText(btn) {{
  const ta = btn.closest('.section-label').nextElementSibling;
  navigator.clipboard.writeText(ta.value).then(() => {{
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
function copyCmd(btn, text) {{
  navigator.clipboard.writeText(text).then(() => {{
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
function dismissCard(id, btn, cmd) {{
  navigator.clipboard.writeText(cmd);
  const card = document.getElementById(id);
  btn.textContent = '✓';
  btn.style.color = '#94a3b8';
  card.style.transition = 'opacity 0.35s, max-height 0.4s, margin 0.4s';
  card.style.opacity = '0';
  card.style.overflow = 'hidden';
  card.style.maxHeight = card.scrollHeight + 'px';
  setTimeout(() => {{ card.style.maxHeight = '0'; card.style.marginBottom = '0'; }}, 350);
  setTimeout(() => {{ card.remove(); }}, 750);
}}
</script>
</body>
</html>"""


def main() -> None:
    conn = get_connection()

    ready = [dict(r) for r in conn.execute("""
        SELECT title, company, location, fit_score,
               application_url, url, tailored_resume_path, cover_letter_path, site
        FROM jobs
        WHERE tailored_resume_path IS NOT NULL
          AND cover_letter_path IS NOT NULL
          AND eligibility_allowed = 1
          AND fit_score >= 7
          AND (apply_status IS NULL OR (apply_status = 'failed' AND apply_attempts < 99))
          AND apply_status IS NOT 'skip'
        ORDER BY fit_score DESC, discovery_score DESC
    """).fetchall()]

    manual = [dict(r) for r in conn.execute("""
        SELECT title, company, location, fit_score,
               application_url, url, tailored_resume_path, cover_letter_path
        FROM jobs
        WHERE company = 'Grafana Labs'
          AND apply_status = 'manual'
          AND tailored_resume_path IS NOT NULL
          AND cover_letter_path IS NOT NULL
        ORDER BY fit_score DESC
    """).fetchall()]

    html = build_html(ready, manual)
    out = config.APP_DIR / "apply_queue.html"
    out.write_text(html, encoding="utf-8")
    console.print(f"[green]Apply queue written to {out}[/green]")
    console.print(f"  {len(ready)} ready jobs + {len(manual)} Grafana Labs (email verify)")
    console.print(f"  [dim]file://{out}[/dim]")

    try:
        import os
        env = {k: v for k, v in os.environ.items() if k != "LD_LIBRARY_PATH"}
        subprocess.Popen(["xdg-open", str(out)], env=env)
        console.print("[dim]Opening in browser...[/dim]")
    except Exception:
        pass


if __name__ == "__main__":
    main()
