"""Background jobs: daily morning briefing + periodic full reindex.

Kept intentionally minimal — apscheduler in-process, no external broker. Jobs
are best-effort; failures are logged and the next tick will retry.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pa.agent import Conversation, run_turn
from pa.memory.index import get_index
from pa.vault.manager import get_vault

log = logging.getLogger(__name__)


_BRIEFING_PROMPT = (
    "Write me a short morning briefing for {today}. Include: "
    "(1) the most important open reminders, (2) friends I'm overdue to reach out "
    "to based on each person note's `last_contact` and `cadence_weeks`, and "
    "(3) any threads from yesterday's journal worth picking up. Keep it under "
    "ten bullet points."
)


async def _morning_briefing() -> None:
    try:
        get_vault().ensure_mounted()
    except Exception as exc:  # noqa: BLE001
        log.info("morning briefing skipped (vault not mounted): %s", exc)
        return

    conv = Conversation()
    prompt = _BRIEFING_PROMPT.format(today=date.today().isoformat())
    briefing = ""
    async for event in run_turn(conv, prompt):
        if event.kind == "token" and event.text:
            briefing += event.text

    if not briefing.strip():
        return

    vault = get_vault()
    journal_path = vault.journal_path_for(date.today())
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    existing = journal_path.read_text(encoding="utf-8") if journal_path.exists() else ""
    block = f"\n\n## Morning briefing — {datetime.now().strftime('%H:%M')}\n\n{briefing.strip()}\n"
    journal_path.write_text(existing + block, encoding="utf-8")

    _try_notify("Aleph", "Morning briefing ready in today's journal.")


async def _reindex() -> None:
    try:
        get_vault().ensure_mounted()
    except Exception as exc:  # noqa: BLE001
        log.info("reindex skipped (vault not mounted): %s", exc)
        return
    result = await get_index().reindex_all()
    log.info("reindex complete: %s", result)


def _try_notify(title: str, message: str) -> None:
    """Fire a macOS notification via osascript. Silent failure if unavailable."""
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            check=False,
            timeout=2,
        )


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _morning_briefing,
        CronTrigger(hour=8, minute=0),
        id="morning-briefing",
        replace_existing=True,
    )
    scheduler.add_job(
        _reindex,
        IntervalTrigger(hours=6),
        id="full-reindex",
        replace_existing=True,
    )
    return scheduler
