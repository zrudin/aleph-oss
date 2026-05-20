"""Web search + fetch tools, privacy-hardened.

- `web_search` queries DuckDuckGo via the `ddgs` package. No API key, no
  cookies, no account. Bursty requests can hit a 202 rate-limit response;
  we back off and retry a bounded number of times.
- `web_fetch` downloads a single page through the hardened net client and
  extracts main-text with trafilatura. JS is never executed.

Neither tool touches the vault. Search queries should come from the model's
current question, not from vault contents.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pa.config import settings
from pa.net import UnsafeURLError, safe_get

log = logging.getLogger(__name__)


def _run_blocking_search(query: str, max_results: int, region: str) -> list[dict[str, Any]]:
    # ddgs is sync; we shove it onto a thread.
    from ddgs import DDGS

    with DDGS() as client:
        return list(client.text(query, region=region, max_results=max_results))


async def web_search(
    query: str,
    max_results: int = 5,
    region: str | None = None,
) -> dict[str, Any]:
    """Search the public web via DuckDuckGo.

    Returns up to `max_results` hits as {title, url, snippet}. On rate-limit,
    backs off exponentially and retries.
    """
    if not isinstance(query, str) or not query.strip():
        return {"error": "query must be a non-empty string"}
    max_results = max(1, min(int(max_results or 5), 10))
    region = region or settings.web_search_region

    try:
        from ddgs.exceptions import RatelimitException
    except ImportError:  # older versions
        RatelimitException = Exception  # type: ignore[assignment,misc]

    delay = 1.0
    last_err: Exception | None = None
    for attempt in range(settings.web_search_max_retries):
        try:
            raw = await asyncio.to_thread(_run_blocking_search, query, max_results, region)
            results = [
                {
                    "title": r.get("title") or "",
                    "url": r.get("href") or r.get("url") or "",
                    "snippet": r.get("body") or "",
                }
                for r in raw
                if (r.get("href") or r.get("url"))
            ]
            return {"query": query, "results": results}
        except RatelimitException as exc:
            last_err = exc
            log.info("ddgs rate-limited (attempt %d), sleeping %.1fs", attempt + 1, delay)
            await asyncio.sleep(delay)
            delay *= 2
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"}

    return {"error": f"rate limited after {settings.web_search_max_retries} retries: {last_err}"}


async def web_fetch(url: str, max_chars: int = 20000) -> dict[str, Any]:
    """Download a public web page and return extracted main-text."""
    if not isinstance(url, str) or not url.strip():
        return {"error": "url must be a non-empty string"}
    max_chars = max(500, min(int(max_chars or 20000), 200000))

    try:
        response = await safe_get(url)
    except UnsafeURLError as exc:
        return {"error": f"refused: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}

    html = response.text
    title, text = _extract(html)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"

    return {
        "url": str(response.url),
        "title": title,
        "text": text,
    }


def _extract(html: str) -> tuple[str, str]:
    """Pull a title + main-text from raw HTML via trafilatura."""
    try:
        import trafilatura
        from trafilatura.metadata import extract_metadata
    except ImportError:
        return "", html[:5000]

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        favor_recall=False,
    ) or ""

    title = ""
    try:
        meta = extract_metadata(html)
        if meta and meta.title:
            title = meta.title
    except Exception:  # noqa: BLE001
        pass

    return title, text
