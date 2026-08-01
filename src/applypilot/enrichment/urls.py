"""URL normalization helpers shared by detail enrichment and tests."""

from urllib.parse import urljoin


def _load_base_urls() -> dict[str, str | None]:
    """Load site base URLs through the runtime configuration loader."""
    from applypilot.config import load_base_urls

    return load_base_urls()


def resolve_url(raw_url: str, site: str) -> str | None:
    """Resolve a stored board URL to an absolute detail URL."""
    if not raw_url:
        return None

    if raw_url.startswith(("http://", "https://")):
        return raw_url

    if site == "WelcomeToTheJungle":
        return None

    if site == "Randstad Canada" and "/" not in raw_url:
        return f"https://www.randstad.ca/jobs/search/{raw_url}"

    if site == "4DayWeek" and raw_url in ("/", "/jobs"):
        return None

    # Working Nomads emits bare slugs for detail links. Its search URL is
    # `/jobs`, so the configured base deliberately includes that path.
    if site == "Working Nomads" and raw_url in ("/", "/jobs", "/jobs/"):
        return None

    base = _load_base_urls().get(site)
    if not base:
        return None

    if ";jsessionid=" in raw_url:
        raw_url = raw_url.split(";jsessionid=")[0]

    return urljoin(base, raw_url)
