"""Vault layout: relative paths and directory names used throughout the app."""

from __future__ import annotations

PROFILE_FILE = "profile.md"

PEOPLE_DIR = "people"
INTERESTS_DIR = "interests"
PROJECTS_DIR = "projects"
WORK_DIR = "work"
JOURNAL_DIR = "journal"
REMINDERS_DIR = "reminders"
INBOX_DIR = "inbox"
THREADS_DIR = "threads"

REMINDERS_ACTIVE = "reminders/active.md"
REMINDERS_ARCHIVE = "reminders/archive.md"

SYSTEM_DIR = ".pa"
INDEX_SUBDIR = "index.lance"

BOOTSTRAP_DIRECTORIES: list[str] = [
    PEOPLE_DIR,
    INTERESTS_DIR,
    PROJECTS_DIR,
    WORK_DIR,
    JOURNAL_DIR,
    REMINDERS_DIR,
    INBOX_DIR,
    THREADS_DIR,
    SYSTEM_DIR,
]
