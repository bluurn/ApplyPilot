<!-- logo here -->

> **⚠️ ApplyPilot** is the original open-source project, created by [Pickle-Pixel](https://github.com/Pickle-Pixel) and first published on GitHub on **February 17, 2026**. We are **not affiliated** with applypilot.app, useapplypilot.com, or any other product using the "ApplyPilot" name. These sites are **not associated with this project** and may misrepresent what they offer. If you're looking for the autonomous, open-source job application agent — you're in the right place.

# ApplyPilot

**Applied to 1,000 jobs in 2 days. Fully autonomous. Open source.**

[![PyPI version](https://img.shields.io/pypi/v/applypilot?color=blue)](https://pypi.org/project/applypilot/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Pickle-Pixel/ApplyPilot?style=social)](https://github.com/Pickle-Pixel/ApplyPilot)
[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/S6S01UL5IO)




https://github.com/user-attachments/assets/7ee3417f-43d4-4245-9952-35df1e77f2df


---

## What It Does

ApplyPilot is a 6-stage autonomous job application pipeline. It discovers jobs across 5+ boards, scores them against your resume with AI, tailors your resume per job, writes cover letters, and **submits applications for you**. It navigates forms, uploads documents, answers screening questions, all hands-free.

Start with a daily review, then run or apply as needed.

```bash
pip install applypilot
pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex
applypilot init          # one-time setup: resume, profile, preferences, API keys
applypilot doctor        # verify your setup — shows what's installed and what's missing
applypilot today         # ranked briefing: new, best, watchlist, and applied jobs
applypilot run           # discover > enrich > score > tailor > cover letters
applypilot run -w 4      # same but parallel (4 threads for discovery/enrichment)
applypilot apply         # autonomous browser-driven submission
applypilot apply -w 3    # parallel apply (3 Chrome instances)
applypilot apply --dry-run  # fill forms without submitting
```

> **Why two install commands?** `python-jobspy` pins an exact numpy version in its metadata that conflicts with pip's resolver, but works fine at runtime with any modern numpy. The `--no-deps` flag bypasses the resolver; the second command installs jobspy's actual runtime dependencies. Everything except `python-jobspy` installs normally.

### Nix

The flake exports a complete package with JobSpy, Chromium, and Playwright
runtime configuration:

```bash
nix run "git+https://github.com/bluurn/ApplyPilot.git?ref=refs/heads/feat/eu-search-profile" -- --help
nix profile install "git+https://github.com/bluurn/ApplyPilot.git?ref=refs/heads/feat/eu-search-profile"
```

For a declarative NixOS or Home Manager installation, add this flake as an
input and install `inputs.applypilot.packages.${system}.default`.

---

## Two Paths

### Full Pipeline (recommended)
**Requires:** Python 3.11+, Node.js (for npx), Gemini API key (free), Claude Code CLI, Chrome

Runs all 6 stages, from job discovery to autonomous application submission. This is the full power of ApplyPilot.

### Semi-Automatic (discovery + tailoring + manual apply queue)
**Requires:** Python 3.11+, Gemini API key (free)

Runs stages 1–5 automatically, then generates a browser-based apply queue for manual submission. Recommended when auto-apply is blocked by ATS friction (Greenhouse email verification, CAPTCHA walls, SSO-only login).

```bash
applypilot run                  # discover > enrich > score > tailor > cover letters > PDFs
applypilot apply-queue          # generate ~/.applypilot/apply_queue.html
# open apply_queue.html in browser — work through each job manually
applypilot apply --mark-applied URL   # track each submission in the DB
applypilot apply --dismiss URL        # hide a job from the queue permanently
```

The apply queue page shows each job as a card with a direct link to the ATS form, the cover letter text in a one-click copy box, a button to open the tailored resume PDF, and the `--mark-applied` command to run after you submit. Click the **✕** button on any card to instantly hide it and copy the `--dismiss` command to your clipboard. Progress is tracked in the same database as the automated pipeline.

**When auto-apply is blocked by a specific ATS**, add it to `~/.applypilot/config/sites.yaml` so the pipeline skips it automatically and leaves those jobs for the manual queue:

```yaml
# ~/.applypilot/config/sites.yaml
manual_ats:
  - "boards.greenhouse.io/mycompany"   # email verification after submit
  - "ibegin.tcsapps.com"              # unsolvable CAPTCHA
```

### Discovery + Tailoring Only
**Requires:** Python 3.11+, Gemini API key (free)

Runs stages 1–5: discovers jobs, scores them, tailors your resume, generates cover letters. You submit applications manually with the AI-prepared materials.

---

## The Pipeline

| Stage | What Happens |
|-------|-------------|
| **1. Discover** | Scrapes 5 job boards + 44 Workday portals + 10 Greenhouse boards + 15 Lever sites + 23 Ashby boards + 30 direct career sites |
| **2. Enrich** | Fetches full job descriptions via JSON-LD, CSS selectors, or AI-powered extraction |
| **3. Score** | AI rates every job 1-10 based on your resume and preferences. Only high-fit jobs proceed |
| **4. Tailor** | AI rewrites your resume per job: reorganizes, emphasizes relevant experience, adds keywords. Never fabricates |
| **5. Cover Letter** | AI generates a targeted cover letter per job |
| **6. Auto-Apply** | Claude Code navigates application forms, fills fields, uploads documents, answers questions, and submits |

Each stage is independent. Run them all or pick what you need.

---

## ApplyPilot vs The Alternatives

| Feature | ApplyPilot | AIHawk | Manual |
|---------|-----------|--------|--------|
| Job discovery | 5 boards + Workday + Greenhouse + Lever + Ashby + direct sites | LinkedIn only | One board at a time |
| AI scoring | 1-10 fit score per job | Basic filtering | Your gut feeling |
| Resume tailoring | Per-job AI rewrite | Template-based | Hours per application |
| Auto-apply | Full form navigation + submission | LinkedIn Easy Apply only | Click, type, repeat |
| Supported sites | Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs, 44 Workday portals, 10 Greenhouse boards, 15 Lever sites, 23 Ashby boards, 30 direct sites | LinkedIn | Whatever you open |
| License | AGPL-3.0 | MIT | N/A |

---

## Requirements

| Component | Required For | Details |
|-----------|-------------|---------|
| Python 3.11+ | Everything | Core runtime |
| Node.js 18+ | Auto-apply | Needed for `npx` to run Playwright MCP server |
| Gemini API key | Scoring, tailoring, cover letters | Free tier (15 RPM / 1M tokens/day) is enough |
| Chrome/Chromium | Auto-apply | Auto-detected on most systems |
| Claude Code CLI | Auto-apply | Install from [claude.ai/code](https://claude.ai/code) |

**Gemini API key is free.** Get one at [aistudio.google.com](https://aistudio.google.com). OpenAI and local models (Ollama/llama.cpp) are also supported.

### Optional

| Component | What It Does |
|-----------|-------------|
| CapSolver API key | Solves CAPTCHAs during auto-apply (hCaptcha, reCAPTCHA, Turnstile, FunCaptcha). Without it, CAPTCHA-blocked applications just fail gracefully |

> **Note:** python-jobspy is installed separately with `--no-deps` because it pins an exact numpy version in its metadata that conflicts with pip's resolver. It works fine with modern numpy at runtime.

---

## Configuration

All generated by `applypilot init`:

### `profile.json`
Your personal data in one structured file: contact info, work authorization, compensation, experience, skills, resume facts (preserved during tailoring), and EEO defaults. Powers scoring, tailoring, and form auto-fill.

### `searches.yaml`
Job search queries, target titles, locations, boards, configurable deterministic
ranking weights, and a priority-company `watchlist`. Watchlist companies are
searched first and their jobs are highlighted in daily, status, and dashboard
output.

### `.env`
API keys and runtime config: `GEMINI_API_KEY`, `LLM_MODEL`, `CAPSOLVER_API_KEY` (optional).

### Package configs (shipped with ApplyPilot)
- `config/employers.yaml` and `config/employers/` - profile-aware Workday employer registry (44 preconfigured)
- `config/greenhouse.yaml` and `config/greenhouse/` - profile-aware Greenhouse board registry (10 preconfigured)
- `config/lever.yaml` and `config/lever/` - profile-aware Lever site registry (15 preconfigured)
- `config/ashby.yaml` and `config/ashby/` - profile-aware Ashby board registry (23 preconfigured)
- `config/sites.yaml` - Direct career sites (30+), blocked sites, base URLs, manual ATS domains
- `config/searches.example.yaml` - Example search configuration

---

## How Stages Work

### Discover
Queries Indeed, LinkedIn, Glassdoor, ZipRecruiter, and Google Jobs via JobSpy. Scrapes 44 Workday employer portals, 10 Greenhouse boards, 15 Lever sites, and 23 Ashby boards from profile-aware registries, then checks selected direct career sites with custom extractors. A shared policy rejects incompatible local and country-restricted remote roles while preserving explicit Europe locations, worldwide or unspecified remote roles, and jobs offering relocation or visa sponsorship. ATS and direct-site failures are isolated, successful Smart Extract selectors are reused within a crawl, and all sources deduplicate jobs. Each retained job also receives an inspectable deterministic rank from configurable technical, geography, relocation, salary, and watchlist signals; the separate AI fit score is preserved.

### Enrich
Visits each job URL and extracts the full description. 3-tier cascade: JSON-LD structured data, then CSS selector patterns, then AI-powered extraction for unknown layouts.

### Score
AI scores shortlisted jobs 1-10 against your profile. The shortlist uses the configurable deterministic discovery rank and always includes watchlist jobs, preventing broad discovery from generating uncontrolled paid LLM usage. 9-10 = strong match, 7-8 = good, 5-6 = moderate, 1-4 = skip. Only jobs above your threshold proceed to tailoring.

### Tailor
Generates a custom resume per job: reorders experience, emphasizes relevant skills, incorporates keywords from the job description. Your `resume_facts` (companies, projects, metrics) are preserved exactly. The AI reorganizes but never fabricates.

Use the persistent shortlist to keep tailoring controlled:

```bash
applypilot shortlist add 'https://company.example/jobs/123'
applypilot shortlist list
applypilot shortlist remove 'https://company.example/jobs/123'
applypilot run tailor --shortlist
```

Both the source URL and the final application URL are accepted. Duplicate
country variants resolve to one canonical job.

### Cover Letter
Writes a targeted cover letter per job referencing the specific company, role, and how your experience maps to their requirements.

### Auto-Apply
Claude Code launches a Chrome instance, navigates to each application page, detects the form type, fills personal information and work history, uploads the tailored resume and cover letter, answers screening questions with AI, and submits. A live dashboard shows progress in real-time.

The Playwright MCP server is configured automatically at runtime per worker. No manual MCP setup needed.

**Known blockers** that cause automatic submission to fail:

| Blocker | Behaviour | Fix |
|---------|-----------|-----|
| Greenhouse email verification | Form submits but requires an 8-char code sent to your inbox | Add to `manual_ats` in `sites.yaml`; apply manually |
| Unsolvable CAPTCHA | hCaptcha / Cloudflare challenge in headless mode | Add CapSolver key, or add to `manual_ats` |
| SSO-only login | Google / Microsoft OAuth wall | Marked `sso_required`; cannot be automated |
| Account-required ATS | Must create an account the agent can't verify | Marked `account_required`; apply manually |

Jobs blocked by any of the above are marked with a permanent failure reason and skipped on retry. Use the apply queue for these.

```bash
# Utility modes (no Chrome/Claude needed)
applypilot apply --mark-applied URL    # manually mark a job as applied
applypilot apply --mark-failed URL     # manually mark a job as failed
applypilot apply --dismiss URL         # permanently hide a job from the apply queue
applypilot apply --reset-failed        # reset all failed jobs for retry
applypilot apply --gen --url URL       # generate prompt file for manual debugging
```

---

## CLI Reference

```
applypilot init                         # First-time setup wizard
applypilot doctor                       # Verify setup, diagnose missing requirements
applypilot shortlist add URL            # Select one canonical job for tailoring
applypilot shortlist list               # Review selected jobs in priority order
applypilot shortlist remove URL         # Remove a selected job
applypilot run tailor --shortlist       # Tailor only explicitly selected jobs
applypilot run [stages...]              # Run pipeline stages (or 'all')
applypilot run --workers 4              # Parallel discovery/enrichment
applypilot run --stream                 # Concurrent stages (streaming mode)
applypilot run --min-score 8            # Override score threshold
applypilot run --dry-run                # Preview without executing
applypilot run --validation lenient     # Relax validation (recommended for Gemini free tier)
applypilot run --validation strict      # Strictest validation (retries on any banned word)
applypilot apply                        # Launch auto-apply
applypilot apply --workers 3            # Parallel browser workers
applypilot apply --dry-run              # Fill forms without submitting
applypilot apply --continuous           # Run forever, polling for new jobs
applypilot apply --headless             # Headless browser mode
applypilot apply --url URL              # Apply to a specific job
applypilot apply --dismiss URL         # Permanently hide a job from the apply queue
applypilot apply-queue                  # Generate apply_queue.html for manual submission
applypilot workday-health               # Validate configured Workday CXS endpoints
applypilot today                         # Daily ranked job-search briefing
applypilot today --days 3 --limit 20     # Adjust recency window and section size
applypilot status                       # Pipeline statistics
applypilot dashboard                    # Open HTML results dashboard
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

---

## License

ApplyPilot is licensed under the [GNU Affero General Public License v3.0](LICENSE).

You are free to use, modify, and distribute this software. If you deploy a modified version as a service, you must release your source code under the same license.
