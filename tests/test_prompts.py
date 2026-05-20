"""Tests for prompt assembly — particularly first-run onboarding detection."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

from pa import threads as threads_mod
from pa.prompts import (
    RECENT_NOTES_DAYS,
    STALE_PROJECT_DAYS,
    is_first_run,
    render_bootstrap_context,
)
from pa.vault.conventions import (
    INTERESTS_DIR,
    PEOPLE_DIR,
    PROFILE_FILE,
    PROJECTS_DIR,
    REMINDERS_ACTIVE,
)
from pa.vault.note import Note


def _populate_section(profile_path, heading: str, body: str) -> None:
    note = Note.load(profile_path)
    needle = f"## {heading}\n"
    assert needle in note.body, f"profile template missing `## {heading}`"
    note.body = note.body.replace(needle, f"{needle}\n{body}\n", 1)
    note.save()


def test_is_first_run_true_on_fresh_bootstrap(temp_vault):
    assert is_first_run(temp_vault) is True


def test_render_bootstrap_includes_first_run_block_on_fresh_vault(temp_vault):
    ctx = render_bootstrap_context(temp_vault)
    assert "## First-run onboarding" in ctx
    # The instructions should mention the structured-edit tools we expect
    # the agent to call.
    assert "update_section" in ctx
    assert "update_frontmatter" in ctx


def test_is_first_run_false_after_marker_set_true(temp_vault):
    profile_path = temp_vault.root / PROFILE_FILE
    note = Note.load(profile_path)
    note.metadata["first_run_complete"] = True
    note.save()
    assert is_first_run(temp_vault) is False
    assert "## First-run onboarding" not in render_bootstrap_context(temp_vault)


def test_is_first_run_true_while_marker_still_false_even_with_one_section_populated(
    temp_vault,
):
    """Onboarding asks one question per turn; after Q2 the Bio section is
    populated but Q3/Q4 still need to fire. The marker is the source of truth,
    not section emptiness."""
    profile_path = temp_vault.root / PROFILE_FILE
    _populate_section(profile_path, "Bio", "Software engineer in NYC.")
    # Marker is still false from the template.
    assert is_first_run(temp_vault) is True


def test_is_first_run_false_on_legacy_vault_without_marker(temp_vault):
    """A pre-existing vault that predates the marker should not re-onboard the
    user. Detection falls back to a structural check."""
    profile_path = temp_vault.root / PROFILE_FILE
    note = Note.load(profile_path)
    del note.metadata["first_run_complete"]
    note.body = note.body.replace(
        "## Bio\n", "## Bio\n\nLong-established user with content.\n", 1
    )
    note.save()
    assert is_first_run(temp_vault) is False


def test_is_first_run_false_when_legacy_vault_has_people(temp_vault):
    profile_path = temp_vault.root / PROFILE_FILE
    note = Note.load(profile_path)
    del note.metadata["first_run_complete"]
    note.save()
    (temp_vault.root / PEOPLE_DIR / "alice.md").write_text(
        "---\ntype: person\nname: Alice\n---\n# Alice\n", encoding="utf-8"
    )
    assert is_first_run(temp_vault) is False


def test_is_first_run_false_when_legacy_vault_has_projects(temp_vault):
    profile_path = temp_vault.root / PROFILE_FILE
    note = Note.load(profile_path)
    del note.metadata["first_run_complete"]
    note.save()
    (temp_vault.root / PROJECTS_DIR / "rebuild-x.md").write_text(
        "---\ntype: project\nname: x\n---\n# X\n", encoding="utf-8"
    )
    assert is_first_run(temp_vault) is False


# ---- Step 3: bootstrap context enrichment ----------------------------------


def _mark_onboarded(vault) -> None:
    """Flip the first-run marker so digest/threads sections become inspectable
    without the `## First-run onboarding` block dominating the rendered output."""
    note = Note.load(vault.root / PROFILE_FILE)
    note.metadata["first_run_complete"] = True
    note.save()


def _write_raw(path, frontmatter_dict: dict, body: str = "") -> None:
    """Bypass `Note.save()` so we can persist `updated` values older than now."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in frontmatter_dict.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_yesterday_journal_appears_when_present(temp_vault):
    _mark_onboarded(temp_vault)
    yesterday = date.today() - timedelta(days=1)
    journal_path = temp_vault.journal_path_for(yesterday)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text(
        f"# {yesterday.isoformat()}\n\n## What happened\n\nShipped Step 2.\n",
        encoding="utf-8",
    )

    ctx = render_bootstrap_context(temp_vault)
    assert "# Yesterday's journal" in ctx
    assert "Shipped Step 2." in ctx
    assert yesterday.isoformat() in ctx


def test_yesterday_journal_absent_when_no_file(temp_vault):
    _mark_onboarded(temp_vault)
    ctx = render_bootstrap_context(temp_vault)
    assert "# Yesterday's journal" not in ctx


def test_overdue_reminders_in_digest(temp_vault):
    _mark_onboarded(temp_vault)
    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    far_past = (today - timedelta(days=30)).isoformat()
    future = (today + timedelta(days=5)).isoformat()
    (temp_vault.root / REMINDERS_ACTIVE).write_text(
        "# Active reminders\n\n"
        f"- [ ] file taxes (due {past})\n"
        f"- [ ] renew lease (due {far_past})\n"
        f"- [ ] book flights (due {future})\n"
        "- [x] already done (due 2020-01-01)\n"
        "- [ ] no due date set\n",
        encoding="utf-8",
    )

    ctx = render_bootstrap_context(temp_vault)
    assert "## Today digest" in ctx
    digest_overdue = ctx.split("### Overdue reminders", 1)[1].split("###", 1)[0]
    assert "file taxes" in digest_overdue
    assert "renew lease" in digest_overdue
    # Sorted ascending → far-past entry comes first within the digest section.
    assert digest_overdue.index("renew lease") < digest_overdue.index("file taxes")
    # Future, completed, and undated lines must not be classified overdue.
    assert "book flights" not in digest_overdue
    assert "already done" not in digest_overdue
    assert "no due date set" not in digest_overdue


def test_people_overdue_by_cadence(temp_vault):
    _mark_onboarded(temp_vault)
    today = date.today()
    # 6 weeks ago, cadence 4 → overdue by 2 weeks.
    _write_raw(
        temp_vault.root / PEOPLE_DIR / "alice.md",
        {
            "type": "person",
            "name": "Alice",
            "last_contact": (today - timedelta(weeks=6)).isoformat(),
            "cadence_weeks": 4,
        },
        "# Alice\n",
    )
    # Recent contact → not overdue.
    _write_raw(
        temp_vault.root / PEOPLE_DIR / "bob.md",
        {
            "type": "person",
            "name": "Bob",
            "last_contact": (today - timedelta(days=2)).isoformat(),
            "cadence_weeks": 4,
        },
        "# Bob\n",
    )
    # Missing cadence_weeks → skipped silently.
    _write_raw(
        temp_vault.root / PEOPLE_DIR / "carol.md",
        {
            "type": "person",
            "name": "Carol",
            "last_contact": (today - timedelta(weeks=20)).isoformat(),
        },
        "# Carol\n",
    )
    # Long-overdue person (40w past a 2w cadence) — should sort above Alice.
    _write_raw(
        temp_vault.root / PEOPLE_DIR / "dave.md",
        {
            "type": "person",
            "name": "Dave",
            "last_contact": (today - timedelta(weeks=42)).isoformat(),
            "cadence_weeks": 2,
        },
        "# Dave\n",
    )

    ctx = render_bootstrap_context(temp_vault)
    assert "### People overdue to contact" in ctx
    assert "Alice" in ctx
    assert "Dave" in ctx
    assert "Bob" not in ctx
    assert "Carol" not in ctx
    # Most-overdue first.
    assert ctx.index("Dave") < ctx.index("Alice")


def test_stale_active_projects(temp_vault):
    _mark_onboarded(temp_vault)
    today = date.today()
    stale_dt = (
        datetime.combine(today - timedelta(days=STALE_PROJECT_DAYS + 5), datetime.min.time())
        .replace(tzinfo=UTC)
        .isoformat(timespec="seconds")
    )
    fresh_dt = (
        datetime.combine(today - timedelta(days=1), datetime.min.time())
        .replace(tzinfo=UTC)
        .isoformat(timespec="seconds")
    )

    _write_raw(
        temp_vault.root / PROJECTS_DIR / "stale-active.md",
        {"type": "project", "name": "Stale Active", "status": "active", "updated": stale_dt},
        "# Stale Active\n",
    )
    _write_raw(
        temp_vault.root / PROJECTS_DIR / "fresh-active.md",
        {"type": "project", "name": "Fresh Active", "status": "active", "updated": fresh_dt},
        "# Fresh Active\n",
    )
    _write_raw(
        temp_vault.root / PROJECTS_DIR / "stale-archived.md",
        {"type": "project", "name": "Stale Archived", "status": "archived", "updated": stale_dt},
        "# Stale Archived\n",
    )

    ctx = render_bootstrap_context(temp_vault)
    assert f"### Active projects with no update in {STALE_PROJECT_DAYS}+ days" in ctx
    assert "Stale Active" in ctx
    assert "Fresh Active" not in ctx
    assert "Stale Archived" not in ctx


def test_recently_modified_notes(temp_vault):
    _mark_onboarded(temp_vault)
    fresh = temp_vault.root / INTERESTS_DIR / "rust.md"
    fresh.parent.mkdir(parents=True, exist_ok=True)
    fresh.write_text("# Rust\n", encoding="utf-8")

    old = temp_vault.root / INTERESTS_DIR / "ancient.md"
    old.write_text("# Ancient\n", encoding="utf-8")
    old_ts = (datetime.now() - timedelta(days=RECENT_NOTES_DAYS + 5)).timestamp()
    os.utime(old, (old_ts, old_ts))

    ctx = render_bootstrap_context(temp_vault)
    assert f"### Recently modified notes (last {RECENT_NOTES_DAYS} days)" in ctx
    assert "interests/rust.md" in ctx
    assert "interests/ancient.md" not in ctx
    # Profile is rendered explicitly above; don't double-list it here.
    assert "profile.md" not in ctx.split("### Recently modified notes", 1)[1]


def test_recent_threads_block(temp_vault):
    _mark_onboarded(temp_vault)
    titles = ["alpha topic", "beta topic", "gamma topic", "delta topic"]
    for title in titles:
        t = threads_mod.create_thread(temp_vault, title=title)
        threads_mod.append_message(
            temp_vault,
            t.thread_id,
            threads_mod.Message(role="user", content="hi", timestamp=threads_mod.now_iso()),
        )

    ctx = render_bootstrap_context(temp_vault)
    assert "## Recent threads" in ctx
    # Most recently appended (delta) shown; oldest (alpha) not.
    assert "delta topic" in ctx
    assert "gamma topic" in ctx
    assert "beta topic" in ctx
    assert "alpha topic" not in ctx


def test_no_digest_or_threads_when_empty(temp_vault):
    _mark_onboarded(temp_vault)
    ctx = render_bootstrap_context(temp_vault)
    assert "## Today digest" not in ctx
    assert "## Recent threads" not in ctx


def test_active_reminders_heading_not_duplicated(temp_vault):
    """The bootstrapped active.md starts with `# Active reminders`; the
    bootstrap renderer used to wrap that in another `# Active reminders`
    heading, producing two adjacent identical headings."""
    _mark_onboarded(temp_vault)
    # File comes from the template containing `# Active reminders`.
    ctx = render_bootstrap_context(temp_vault)
    assert ctx.count("# Active reminders") <= 1


def test_first_run_block_is_first_in_context(temp_vault):
    """First-run instructions belong at the very top so the model attends to
    them; burying them below 4-5 mostly-empty sections caused the model to
    skip the per-question persists."""
    ctx = render_bootstrap_context(temp_vault)
    assert ctx.lstrip().startswith("## First-run onboarding"), (
        "Expected first-run instructions at the top of the bootstrap context, "
        f"but got:\n{ctx[:200]}"
    )


def test_first_run_suppresses_digest_and_recent_threads(temp_vault):
    """On a fresh vault, the digest is always empty and the only "recent
    thread" is the one the user is in right now. Surface neither during
    onboarding."""
    # Even with a recent thread in the vault, first-run should suppress
    # the Recent threads block.
    t = threads_mod.create_thread(temp_vault, title="onboarding chat")
    threads_mod.append_message(
        temp_vault,
        t.thread_id,
        threads_mod.Message(role="user", content="hi", timestamp=threads_mod.now_iso()),
    )
    ctx = render_bootstrap_context(temp_vault)
    assert "## First-run onboarding" in ctx
    assert "## Recent threads" not in ctx
    assert "## Today digest" not in ctx
