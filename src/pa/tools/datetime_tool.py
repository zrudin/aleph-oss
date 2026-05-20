"""Time/date for the agent. Local timezone (the user's laptop)."""

from __future__ import annotations

from datetime import datetime


async def current_datetime() -> dict:
    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "weekday": now.strftime("%A"),
        "timezone": str(now.tzinfo),
    }
