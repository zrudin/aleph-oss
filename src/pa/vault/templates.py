"""Note templates for new files. Returns a full Markdown string (frontmatter + body).

Templates are intentionally lean — the agent fills them in over time. Names mirror
the `template` enum in `pa.tools.registry`: profile, person, project, interest, journal.
"""

from __future__ import annotations

from datetime import date

_PROFILE = """\
---
type: profile
name: {name}
---
# {name}

## Bio

## Preferences

## Values

## Current focus
"""

_PERSON = """\
---
type: person
name: {name}
tags: []
last_contact: null
cadence_weeks: null
---
# {name}

## Background

## Recent interactions
"""

_PROJECT = """\
---
type: project
name: {name}
status: active
tags: []
---
# {name}

## Goal

## Status

## Next steps
"""

_INTEREST = """\
---
type: interest
name: {name}
tags: []
---
# {name}

## What I'm exploring

## Notes
"""

_JOURNAL = """\
---
type: journal
date: {today}
---
# {today}

## What happened

## What I learned
"""

_TEMPLATES: dict[str, str] = {
    "profile": _PROFILE,
    "person": _PERSON,
    "project": _PROJECT,
    "interest": _INTEREST,
    "journal": _JOURNAL,
}


def render_template(template_name: str, /, **kwargs) -> str:
    template = _TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"unknown template: {template_name!r}")
    kwargs.setdefault("name", "Untitled")
    kwargs.setdefault("today", date.today().isoformat())
    return template.format(**kwargs)
