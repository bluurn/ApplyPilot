"""HTML renderer for the /pipeline server page."""

from __future__ import annotations

_STAGES = ["discover", "enrich", "score", "tailor", "cover", "pdf"]


def render_pipeline(state: dict, stats: dict) -> str:
    running: bool = state.get("running", False)
    stopped: bool = state.get("stopped", False)
    logs: list[str] = state.get("logs", [])
    result: dict | None = state.get("result")
    finished_at: str = state.get("finished_at") or ""

    # --- stats funnel ---
    total = stats.get("total", 0)
    enriched = stats.get("with_description", 0)
    pending_enrich = stats.get("pending_detail", 0)
    scored = stats.get("scored", 0)
    pending_score = stats.get("scoring_candidates", 0)
    tailored = stats.get("tailored", 0)
    pending_tailor = stats.get("untailored_eligible", 0)
    cover = stats.get("with_cover_letter", 0)
    pending_cover = max(tailored - cover, 0)
    ready = stats.get("ready_to_apply", 0)

    def funnel_box(label: str, count: int, pending: int = 0, color: str = "#60a5fa", key: str = "") -> str:
        if pending:
            pend_html = f'<div class="f-pending" id="f-{key}-pend">{pending} pending</div>'
        else:
            pend_html = f'<div class="f-pending" id="f-{key}-pend" style="display:none">0 pending</div>'
        return f"""<div class="f-box">
          <div class="f-label" style="color:{color}">{label}</div>
          <div class="f-count" id="f-{key}-count">{count:,}</div>
          {pend_html}
        </div>"""

    funnel_html = (
        funnel_box("Total", total, color="#94a3b8", key="total")
        + '<div class="f-arrow">→</div>'
        + funnel_box("Enriched", enriched, pending_enrich, key="enriched")
        + '<div class="f-arrow">→</div>'
        + funnel_box("Scored", scored, pending_score, "#f59e0b", key="scored")
        + '<div class="f-arrow">→</div>'
        + funnel_box("Tailored", tailored, pending_tailor, "#10b981", key="tailored")
        + '<div class="f-arrow">→</div>'
        + funnel_box("Cover Letters", cover, pending_cover, "#a78bfa", key="cover")
        + '<div class="f-arrow">→</div>'
        + funnel_box("Ready to Apply", ready, color="#22c55e", key="ready")
    )

    # --- last run result ---
    last_run_html = ""
    if result and result.get("stages"):
        rows = ""
        for s in result["stages"]:
            status = s.get("status", "")
            ok = status == "ok"
            color = "#22c55e" if ok else ("#f59e0b" if status == "partial" else "#f87171")
            rows += f"""<tr>
              <td>{s['stage']}</td>
              <td style="color:{color}">{status}</td>
              <td>{s.get('elapsed', 0):.1f}s</td>
            </tr>"""
        ts = finished_at[:19].replace("T", " ") if finished_at else ""
        last_run_html = f"""
        <div class="panel" style="margin-bottom:1.5rem">
          <div class="panel-title">Last Run {f'<span class="ts">{ts}</span>' if ts else ''}</div>
          <table class="result-table">
            <thead><tr><th>Stage</th><th>Status</th><th>Elapsed</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    # --- stage checkboxes ---
    stage_checks = ""
    for s in _STAGES:
        stage_checks += f'<label class="stage-label"><input type="checkbox" class="stage-cb" value="{s}"> {s}</label>'

    # --- initial log content ---
    initial_logs = "\n".join(logs) if logs else ""
    initial_offset = len(logs)
    is_running_js = "true" if running else "false"
    run_btn_disabled = 'disabled' if running else ''
    if running:
        status_text, status_class = "Running…", "badge-running"
    elif stopped:
        status_text, status_class = "Stopped", "badge-stopped"
    elif result and not result.get("errors"):
        status_text, status_class = "Done", "badge-done"
    elif result:
        status_text, status_class = "Error", "badge-error"
    else:
        status_text, status_class = "Idle", "badge-idle"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>ApplyPilot — Pipeline</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; overflow: hidden; padding: 2rem; display: flex; flex-direction: column; }}
  .above-log {{ flex: 0 1 auto; overflow-y: auto; }}
  .nav {{ display: flex; gap: 0.5rem; margin-bottom: 1.75rem; }}
  .nav-link {{ font-size: 0.85rem; font-weight: 500; padding: 0.4rem 1rem; border-radius: 6px; text-decoration: none; color: #94a3b8; background: #1e293b; border: 1px solid #334155; transition: all 0.15s; }}
  .nav-link:hover {{ color: #e2e8f0; border-color: #475569; }}
  .nav-link.active {{ background: #1e40af; color: #fff; border-color: #3b82f6; }}
  h1 {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.25rem; }}
  .subtitle {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 2rem; }}
  .panel {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; }}
  .panel-title {{ font-size: 0.8rem; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.75rem; }}
  .ts {{ font-weight: 400; color: #475569; text-transform: none; letter-spacing: 0; }}

  /* Funnel */
  .funnel {{ display: flex; align-items: center; gap: 0; margin-bottom: 1.5rem; flex-wrap: wrap; }}
  .f-box {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 1rem 1.25rem; min-width: 100px; text-align: center; }}
  .f-label {{ font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.35rem; }}
  .f-count {{ font-size: 1.6rem; font-weight: 700; color: #f8fafc; }}
  .f-pending {{ font-size: 0.72rem; color: #f87171; margin-top: 0.25rem; }}
  .f-arrow {{ color: #334155; font-size: 1.2rem; padding: 0 0.4rem; }}

  /* Run panel */
  .run-panel {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.5rem; }}
  .run-row {{ display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end; margin-top: 1rem; }}
  .form-group {{ display: flex; flex-direction: column; gap: 0.3rem; }}
  .form-label {{ font-size: 0.75rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
  .form-input {{ background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 0.4rem 0.65rem; border-radius: 6px; font-size: 0.85rem; width: 80px; }}
  .form-select {{ background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 0.4rem 0.65rem; border-radius: 6px; font-size: 0.85rem; }}
  .stages-row {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.75rem; }}
  .stage-label {{ font-size: 0.8rem; color: #94a3b8; display: flex; align-items: center; gap: 0.3rem; cursor: pointer; }}
  .stage-label input {{ accent-color: #3b82f6; }}
  .btn-run {{ background: #1d4ed8; color: #fff; border: none; padding: 0.55rem 1.5rem; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; margin-top: 0.25rem; }}
  .btn-run:hover:not(:disabled) {{ background: #1e40af; }}
  .btn-run:disabled {{ opacity: 0.45; cursor: not-allowed; }}

  /* Status badge */
  .badge-idle    {{ background: #334155; color: #94a3b8; }}
  .badge-running {{ background: #1d4ed8; color: #fff; animation: pulse 1.5s infinite; }}
  .badge-done    {{ background: #166534; color: #86efac; }}
  .badge-error   {{ background: #7f1d1d; color: #fca5a5; }}
  .badge-stopped {{ background: #78350f; color: #fcd34d; }}
  .btn-stop {{ background: #7f1d1d; color: #fca5a5; border: 1px solid #ef444444; border-radius: 8px; padding: 0.55rem 1.25rem; font-size: 0.9rem; font-weight: 600; cursor: pointer; }}
  .btn-stop:hover {{ background: #991b1b; }}
  .resume-note {{ font-size: 0.8rem; color: #fcd34d; background: #78350f22; border: 1px solid #78350f; border-radius: 6px; padding: 0.5rem 0.85rem; margin-top: 0.75rem; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.6}} }}
  .badge {{ font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.65rem; border-radius: 99px; }}

  /* Result table */
  .result-table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  .result-table th {{ color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; padding: 0.3rem 0.5rem; text-align: left; border-bottom: 1px solid #334155; }}
  .result-table td {{ padding: 0.35rem 0.5rem; border-bottom: 1px solid #1e293b; color: #cbd5e1; }}

  /* Log panel */
  .log-panel {{ background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 1rem 1.25rem; flex: 1 0 200px; display: flex; flex-direction: column; min-height: 0; margin-top: 1.5rem; }}
  .log-pre {{ font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 0.75rem; color: #94a3b8; background: #0f172a; border-radius: 6px; padding: 0.75rem; flex: 1; min-height: 0; overflow-y: auto; white-space: pre-wrap; word-break: break-all; margin-top: 0.75rem; }}
</style>
</head>
<body>
<div class="above-log">
<nav class="nav">
  <a href="/" class="nav-link">Dashboard</a>
  <a href="/queue" class="nav-link">Apply Queue</a>
  <a href="/pipeline" class="nav-link active">Pipeline</a>
</nav>

<h1>Pipeline</h1>
<p class="subtitle">DB state · trigger runs · live logs</p>

<div class="funnel">
{funnel_html}
</div>

<div id="last-run-section">{last_run_html}</div>

<div class="run-panel" style="margin-bottom:1.5rem">
  <div class="panel-title">
    Run Pipeline
    <span class="badge {status_class}" id="status-badge">{status_text}</span>
  </div>
  <div class="stages-row">
    <label class="stage-label"><input type="checkbox" id="cb-all" checked onchange="toggleAll(this)"> <strong>All stages</strong></label>
    <span style="color:#334155;padding:0 0.25rem">|</span>
    {stage_checks}
  </div>
  <div class="run-row">
    <div class="form-group">
      <label class="form-label">Min score</label>
      <input class="form-input" type="number" id="min-score" value="6" min="1" max="10">
    </div>
    <div class="form-group">
      <label class="form-label">Workers</label>
      <input class="form-input" type="number" id="workers" value="4" min="1" max="16">
    </div>
    <div class="form-group">
      <label class="form-label">Tailor limit</label>
      <input class="form-input" type="number" id="tailor-limit" value="20" min="0" max="999">
    </div>
    <div class="form-group">
      <label class="form-label">Validation</label>
      <select class="form-select" id="validation">
        <option value="normal" selected>normal</option>
        <option value="strict">strict</option>
        <option value="lenient">lenient</option>
      </select>
    </div>
    <button class="btn-run" id="run-btn" {run_btn_disabled} onclick="runPipeline()">Run Pipeline</button>
    <button class="btn-stop" id="stop-btn" style="display:{'inline-block' if running else 'none'}" onclick="stopPipeline()">Stop</button>
  </div>
  <div class="resume-note" id="resume-note" style="display:{'block' if stopped else 'none'}">
    Stopped after current job. Click Run Pipeline to resume — each stage skips already-processed jobs.
  </div>
</div>
</div>

<div class="log-panel">
  <div class="panel-title">Live Log</div>
  <pre class="log-pre" id="log-out">{initial_logs}</pre>
</div>

<script>
let logOffset = {initial_offset};
let pollTimer = null;

function toggleAll(cb) {{
  document.querySelectorAll('.stage-cb').forEach(el => {{ el.checked = false; el.disabled = cb.checked; }});
}}
toggleAll(document.getElementById('cb-all'));

function getStages() {{
  const allCb = document.getElementById('cb-all');
  if (allCb.checked) return ['all'];
  const selected = [...document.querySelectorAll('.stage-cb:checked')].map(el => el.value);
  return selected.length ? selected : ['all'];
}}

async function runPipeline() {{
  const body = {{
    stages: getStages(),
    min_score: parseInt(document.getElementById('min-score').value) || 6,
    workers: parseInt(document.getElementById('workers').value) || 4,
    tailor_limit: parseInt(document.getElementById('tailor-limit').value) || 20,
    validation: document.getElementById('validation').value,
  }};
  const resp = await fetch('/pipeline/run', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }});
  const data = await resp.json();
  if (data.ok) {{
    document.getElementById('log-out').textContent = '';
    logOffset = 0;
    setStatus('running');
    document.getElementById('run-btn').disabled = true;
    document.getElementById('stop-btn').style.display = 'inline-block';
    document.getElementById('resume-note').style.display = 'none';
    startPolling();
  }} else {{
    alert(data.error || 'Failed to start pipeline');
  }}
}}

function setStatus(s) {{
  const badge = document.getElementById('status-badge');
  badge.className = 'badge badge-' + s;
  badge.textContent = s === 'running' ? 'Running…' : s.charAt(0).toUpperCase() + s.slice(1);
}}

function startPolling() {{
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(poll, 2000);
}}

async function stopPipeline() {{
  document.getElementById('stop-btn').disabled = true;
  await fetch('/pipeline/stop', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: '{{}}'}});
}}

function updateFunnel(s) {{
  function set(key, count, pending) {{
    const c = document.getElementById('f-' + key + '-count');
    const p = document.getElementById('f-' + key + '-pend');
    if (c) c.textContent = count.toLocaleString();
    if (p) {{ p.textContent = pending + ' pending'; p.style.display = pending > 0 ? '' : 'none'; }}
  }}
  const pendCover = Math.max((s.tailored || 0) - (s.with_cover_letter || 0), 0);
  set('total',    s.total || 0, 0);
  set('enriched', s.with_description || 0, s.pending_detail || 0);
  set('scored',   s.scored || 0, s.scoring_candidates || 0);
  set('tailored', s.tailored || 0, s.untailored_eligible || 0);
  set('cover',    s.with_cover_letter || 0, pendCover);
  set('ready',    s.ready_to_apply || 0, 0);
}}

function renderLastRun(result, finishedAt) {{
  if (!result || !result.stages || !result.stages.length) return;
  const ts = finishedAt ? finishedAt.slice(0, 19).replace('T', ' ') : '';
  const rows = result.stages.map(s => {{
    const col = s.status === 'ok' ? '#22c55e' : (s.status === 'partial' ? '#f59e0b' : '#f87171');
    return `<tr><td>${{s.stage}}</td><td style="color:${{col}}">${{s.status}}</td><td>${{(s.elapsed||0).toFixed(1)}}s</td></tr>`;
  }}).join('');
  document.getElementById('last-run-section').innerHTML = `
    <div class="panel" style="margin-bottom:1.5rem">
      <div class="panel-title">Last Run <span class="ts">${{ts}}</span></div>
      <table class="result-table">
        <thead><tr><th>Stage</th><th>Status</th><th>Elapsed</th></tr></thead>
        <tbody>${{rows}}</tbody>
      </table>
    </div>`;
}}

async function poll() {{
  try {{
    const resp = await fetch('/pipeline/state?offset=' + logOffset);
    const data = await resp.json();
    if (data.new_logs && data.new_logs.length) {{
      logOffset += data.new_logs.length;
      const pre = document.getElementById('log-out');
      pre.textContent += data.new_logs.join('\\n') + '\\n';
      pre.scrollTop = pre.scrollHeight;
    }}
    if (data.stats) updateFunnel(data.stats);
    if (!data.running) {{
      clearInterval(pollTimer);
      pollTimer = null;
      document.getElementById('run-btn').disabled = false;
      document.getElementById('stop-btn').style.display = 'none';
      document.getElementById('stop-btn').disabled = false;
      renderLastRun(data.result, data.finished_at);
      if (data.stopped) {{
        setStatus('stopped');
        document.getElementById('resume-note').style.display = 'block';
      }} else {{
        const hasErrors = data.result && data.result.errors && Object.keys(data.result.errors).length;
        setStatus(hasErrors ? 'error' : 'done');
        document.getElementById('resume-note').style.display = 'none';
      }}
    }}
  }} catch(e) {{
    // network blip, keep polling
  }}
}}

if ({is_running_js}) {{ startPolling(); }}
</script>
</body>
</html>"""
