# ApplyPilot Fork Context

This repository is a personal fork of ApplyPilot optimized for the owner's job search. Do not optimize for upstream compatibility when it conflicts with discovery quality, ranking quality, or usability.

## Primary Principle

Every change should improve job discovery quality or make the search workflow more effective.

Priority order:
1. Discovery quality
2. Ranking quality
3. Daily review workflow
4. Application automation

Do not spend meaningful effort on application automation while discovery remains weak.

## User Search Geography

Never infer geography from IP address, VPN exit node, system locale, or current network location.

Ignore Serbia completely. The owner may appear to be in Serbia because of a VPN, but Serbia must not influence discovery, filtering, ranking, or defaults.

Use only explicit configuration. Current intended geography:

- Germany
- European Union / Europe
- Europe-compatible remote roles
- Worldwide remote roles when they are realistically open to European applicants

## Preferred Roles

Current ranking direction:

- Python
- Backend engineering
- Platform or infrastructure-adjacent backend work
- Remote roles
- Germany-based roles
- Roles offering relocation support
- Roles with useful salary information

These preferences should eventually be configurable rather than permanently hardcoded.

## Current Branch

Development currently happens on `feat/eu-search-profile`. Keep work on this branch unless explicitly instructed otherwise.

Do not push changes. The owner pushes manually. Do not run `sudo nixos-rebuild switch`; the owner performs system activation.

## Architecture

### Pipeline Stages

Six sequential stages (`pipeline.py`), each independently runnable:

1. **discover** — JobSpy boards (isolated subprocesses) + Workday portals + Greenhouse + Lever + Ashby + direct career sites
2. **enrich** — fetch full descriptions (JSON-LD → CSS selectors → AI extraction cascade)
3. **score** — LLM fit score 1–10; applied only to deterministic shortlist + watchlist to bound paid usage
4. **tailor** — per-job resume rewrite; `resume_facts` are ground truth, never fabricated
5. **cover** — targeted cover letter per job
6. **pdf** — PDF conversion of tailored resumes and cover letters

CLI entry point: `cli.py` (Typer). All user data lives under `~/.applypilot/` (overridable via `APPLYPILOT_DIR`).

### Configuration System

Two-layer config: package-shipped YAML registries + optional user overrides.

- Package registries: `src/applypilot/config/` — employers, greenhouse, lever, ashby, sites, profiles
- User overrides: `~/.applypilot/config/` — same directory structure; installed package stays immutable
- `config_registry.py` — merges registries; supports `search_profile`/`search_profiles`, recursive dict merge, order-preserving list dedup, legacy single-file fallback
- `config.py` — runtime paths and loaders (`load_sites_config()`, `load_employers_config()`)

**Do not** read package YAML files directly from discovery or enrichment modules. Always go through the loaders in `config.py`.

### Registry Layout

```text
src/applypilot/config/
├── profiles.yaml
├── employers.yaml  (+ employers/)
├── ashby.yaml      (+ ashby/)
├── greenhouse.yaml (+ greenhouse/)
├── lever.yaml      (+ lever/)
└── sites.yaml      (+ sites/)
```

User overrides mirror this structure under `~/.applypilot/config/`. Personal employers, sites, blocks, URL mappings, and profile fragments belong there.

### Discovery Architecture (`src/applypilot/discovery/`)

Each ATS source is isolated — one source failing must never stop the others.

- `jobspy.py` — JobSpy boards in isolated subprocesses with hard timeouts and partial-result retention
- `workday.py` — Workday CXS API
- `greenhouse.py` — Greenhouse public API with per-employer failure isolation
- `lever.py` — Lever Postings API with global/EU instance support
- `ashby.py` — Ashby Job Postings API with compensation data
- `smartextract.py` — direct career site scraping; reuses successful selectors within a crawl
- `watchlist.py` — exact normalized company watchlist matching (not fuzzy)

### Ranking & Filtering

- Deterministic ranking from configurable signals (geography, remote, language, relocation, salary, watchlist) runs before and after enrichment — `scoring/ranking.py`
- LLM fit score is separate; applied only to the deterministic shortlist to prevent unbounded paid LLM usage
- Shared location eligibility logic rejects incompatible geographies while preserving explicit EU locations, worldwide/unspecified remote, and relocation/sponsorship offers
- All eligibility and ranking decisions are logged and inspectable

### Auto-Apply (`src/applypilot/apply/`)

Chrome/Playwright browser launcher that delegates form navigation to the Claude Code CLI. Playwright MCP server is configured automatically per worker at runtime — no manual MCP setup needed.

Never submit applications without explicit user approval. Safe validation command:

```bash
nix run . -- apply --dry-run --headless --limit 1
```

Cover letter requirements enforced by the Python path:

- Full name `Vladimir Suvorov`, never nickname `bluurn`
- Natural introduction after `Dear Hiring Manager,`
- Closing exactly `Best regards,` followed by full name
- Left-aligned prose PDF layout with no resume-style bottom rule

### BAML (`baml_src/`, `src/applypilot/scoring/baml_adapter.py`)

Deferred. Do not enable until deterministic resume-fact extraction, role/bullet selection, and claim validation are stable in the Python path.

## User Data (local, never commit)

- `~/.applypilot/applypilot.db` — SQLite database
- `~/.applypilot/profile.json` — personal data for scoring and form fill
- `~/.applypilot/searches.yaml` — search queries, ranking weights, watchlist
- `~/.applypilot/tailored_resumes/` and `~/.applypilot/cover_letters/` — generated artifacts

## Validation

Run the narrowest relevant tests first, then the full suite:

```bash
pytest tests/test_config_registry.py tests/test_config_runtime.py   # config changes
pytest -q tests/test_chrome.py tests/test_pdf.py                    # apply/PDF changes
pytest                                                               # full suite
ruff check .
pyright
```

The Nix development shell (`nix develop`) provides Python, uv, pytest, ruff, pyright, Chromium, and Playwright with `PYTHONPATH=$PWD/src:$PYTHONPATH` set.

## Engineering Guidelines

- Prefer focused changes with regression tests.
- Treat per-source discovery failures as isolated; one source must not stop the rest.
- Log why jobs are filtered or ranked.
- Keep configuration user-editable; do not silently infer important preferences.
- Do not add abstraction for upstream cleanliness.
- Do not commit: generated files, secrets, personal resumes, API keys, databases, browser profiles, or local search data.
- Ruff line length is 120.

## Before / After Changing Code

Before:
1. Inspect the relevant implementation and tests.
2. Check for existing uncommitted work and do not overwrite it.

After:
1. Run tests.
2. Summarize exactly what changed.
3. Report any tests or checks that could not be run.
4. Commit on the current branch only when explicitly requested.

When a request is ambiguous, choose the option that most directly improves the owner's job discovery quality while keeping behavior configurable.

## Discovery Roadmap

Current coverage (eu profile, all verified healthy):
- Greenhouse: 29 boards, all live-verified (added Wolt, Remote, MongoDB, Netlify, Fastly, Intercom, Mozilla, HelloFresh, Figma, Brex, Stripe, Twilio, Discord, Coinbase, Airtable, Amplitude, Mixpanel, Postman; 14 candidates removed — migrated off Greenhouse)
- Lever: 20 sites, all live-verified (added Contentsquare, Aircall, Swile, BlaBlaCar, Malt; 20 candidates removed — migrated off Lever)
- Ashby: 35 boards (was 23; round 1: dbt Labs, Retool, Prefect, Dagster, Modal, Turso; round 2: Resend, Cal.com, Baseten, Novu, Inngest, Apify)
- Workday: 45 employers (no new additions — all candidates returned 422/401; Workday site_ids cannot be guessed reliably without seeing an actual job posting URL)

Next:
- Continue expanding Workday toward 100+ employers.
- Improve Europe-relevant JobSpy coverage.

### Watchlist

```yaml
watchlist:
  - JetBrains
  - GitLab
  - Canonical
  - Grafana Labs
  - Cloudflare
  - Elastic
  - Datadog
  - Red Hat
```

### Future: Claude Provider Unification

Evaluate using Anthropic/Claude as the common LLM provider for enrichment, scoring, tailoring, and cover letters. Keep provider/model selection configurable. Compare cost, latency, structured-output reliability, and rate limits before migrating defaults. Keep the Claude Code CLI browser agent separate from the batch LLM provider unless a direct API path proves reliable and economical.
