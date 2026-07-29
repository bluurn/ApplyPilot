# ApplyPilot Fork Context

This repository is a personal fork of ApplyPilot optimized for the owner's job search. Do not optimize for upstream compatibility when it conflicts with discovery quality, ranking quality, or usability for this fork.

## Primary Principle

Every change should improve job discovery quality or make the search workflow more effective for the owner.

Priority order:

1. Discovery quality
2. Ranking quality
3. Daily review workflow
4. Application automation

Do not spend meaningful effort polishing application automation while discovery remains weak.

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

Development currently happens on:

`feat/eu-search-profile`

Keep work on this branch unless explicitly instructed otherwise.

## Current Architecture Work

A profile-aware YAML registry layer exists in:

`src/applypilot/config_registry.py`

It supports:

- `search_profile`
- `search_profiles`
- recursive dictionary merge
- order-preserving list deduplication
- legacy single-file fallback
- user registry overrides

Runtime configuration in `src/applypilot/config.py` uses registries from package config plus optional user overrides from:

`$APPLYPILOT_DIR/config`

Normally this is:

`~/.applypilot/config`

Important loaders include:

- `load_sites_config()`
- `load_employers_config()`

Do not bypass these loaders by reading package YAML files directly from discovery or enrichment modules.

## Registry Layout

Package registries may use:

```text
src/applypilot/config/
├── profiles.yaml
├── employers.yaml
├── ashby.yaml
├── greenhouse.yaml
├── lever.yaml
├── sites.yaml
├── employers/
│   └── <fragment>.yaml
├── ashby/
│   └── <fragment>.yaml
├── greenhouse/
│   └── <fragment>.yaml
├── lever/
│   └── <fragment>.yaml
└── sites/
    └── <fragment>.yaml
```

User overrides may use the equivalent structure under:

```text
~/.applypilot/config/
```

The installed package should remain immutable. Personal employers, sites, blocks, URL mappings, and profile fragments belong in the user config directory.

## Completed Work

The fork already includes:

- NixOS / Home Manager packaging
- Chromium and Playwright runtime integration
- development shell with Python, uv, pytest, ruff, pyright, Chromium, and Playwright
- profile-aware config registry
- runtime registry integration in `config.py`
- tests for registry merging and runtime integration
- Workday registry health checking via `applypilot workday-health`
- 44 live Workday portals in the base plus Europe profile registries
- isolated JobSpy board subprocesses with hard timeouts and partial-result retention
- first-class Greenhouse public API discovery with per-employer failure isolation
- 10 verified Europe-relevant Greenhouse boards in the Europe profile,
  including JetBrains
- shared inspectable location eligibility decisions across all discovery sources
- country-restricted remote filtering with relocation and sponsorship preservation
- first-class Lever Postings API discovery with global/EU instance support
- 15 verified Europe-relevant Lever sites in the Europe profile
- first-class Ashby Job Postings API discovery with compensation data
- 23 verified Europe-relevant Ashby boards in the Europe profile

The development shell exports `PYTHONPATH=$PWD/src:$PYTHONPATH`.

## Immediate Next Task

Add a configurable high-priority company watchlist across discovery sources.

Requirements:

1. Load watchlist company names from search configuration.
2. Match normalized source/company names without opaque fuzzy scoring.
3. Search watchlist employers before the remaining registry entries.
4. Preserve watchlist status on discovered jobs in an inspectable database
   field.
5. Surface watchlist jobs prominently in status/dashboard output.
6. Keep missing or temporarily broken watchlist companies visible in results.
7. Add focused ordering, matching, persistence, and reporting tests.

## Discovery Roadmap

### Employer and ATS coverage

- Expand Workday employers to roughly 100–300 useful companies.
- Expand Greenhouse coverage beyond the initial 9 verified boards.
- Expand Lever coverage beyond the initial 15 verified sites.
- Expand Ashby coverage beyond the initial 23 verified boards.
- Improve Europe-relevant JobSpy coverage.
- Extend strong Europe and remote filtering as new source data permits.

### Watchlist

Support a high-priority company watchlist that is checked before general discovery.

Example:

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

Watchlist companies should be searched first and surfaced prominently.

### Ranking

Ranking should account for configurable signals such as:

- remote compatibility
- Germany relevance
- Europe relevance
- Python/backend fit
- relocation support
- salary availability and quality
- preferred companies
- penalties for incompatible geography

Avoid opaque magic scoring. Keep individual signals inspectable and configurable.

### Daily Dashboard

The intended command is:

```bash
applypilot today
```

It should summarize:

- newly discovered jobs
- best matches
- new companies
- already applied jobs
- newly opened roles
- watchlist results

## Engineering Guidelines

- Prefer focused changes with regression tests.
- Preserve existing behavior unless it harms the owner's search goals.
- Avoid adding abstraction merely for upstream cleanliness.
- Keep configuration user-editable.
- Do not silently infer important preferences.
- Log why jobs are filtered or ranked when practical.
- Treat discovery failures per source as isolated failures; one source should not stop the rest of discovery.
- Avoid committing generated files, secrets, personal resumes, API keys, databases, browser profiles, or local search data.

## Validation

For Python changes, run the narrowest relevant tests first, then the full suite when practical:

```bash
pytest tests/test_config_registry.py tests/test_config_runtime.py
pytest
```

Use Ruff and Pyright when changes affect typing, imports, or larger module boundaries:

```bash
ruff check .
pyright
```

## Working Style for Codex

Before changing code:

1. Read this file.
2. Inspect the relevant implementation and tests.
3. Check for existing uncommitted work and do not overwrite it.

After changing code:

1. Run tests.
2. Summarize exactly what changed.
3. Report any tests or checks that could not be run.
4. Create an intentional commit on the current branch when requested.

When a request is ambiguous, choose the option that most directly improves the owner's job discovery quality while keeping the behavior configurable.
