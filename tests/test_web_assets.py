"""Static asset wiring checks for the web UI.

These are deliberately tiny — they don't render JS, they just pin a few
load-bearing strings so a future refactor that drops the AlephThinking
module or removes the Rubik font link fails CI instead of silently
breaking the in-browser experience.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "pa" / "web"


def test_aleph_thinking_module_is_present() -> None:
    module = WEB / "static" / "js" / "aleph-thinking.js"
    assert module.is_file(), "aleph-thinking.js must exist in static/js/"
    text = module.read_text(encoding="utf-8")
    assert "alephThinkingHtml" in text
    assert "startAlephThinkingTimer" in text
    # Triple-aleph row + variable-weight bump are the visual essence of
    # the design; pin them so accidental edits get flagged.
    assert text.count("א") >= 1
    assert "font-variation-settings" in text


def test_message_renderer_uses_thinking_indicator() -> None:
    message_js = (WEB / "static" / "js" / "message.js").read_text(encoding="utf-8")
    assert "aleph-thinking.js" in message_js, (
        "message.js must import the thinking indicator helper"
    )
    assert "alephThinkingHtml" in message_js


def test_chat_view_drives_thinking_timer() -> None:
    chat_view = (WEB / "static" / "js" / "chat-view.js").read_text(encoding="utf-8")
    assert "startAlephThinkingTimer" in chat_view, (
        "chat-view.js must start the elapsed-time timer when a turn begins"
    )


def test_index_template_loads_rubik() -> None:
    index = (WEB / "templates" / "index.html").read_text(encoding="utf-8")
    # The variable axis form is what powers the weight-bump animation,
    # so require the wght@400..700 spec specifically.
    assert "Rubik:wght@400..700" in index


def test_aleph_mark_css_uses_rubik() -> None:
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    # Every Aleph glyph in the app shares the .aleph-mark face. Pin the
    # Rubik font-family so accidental reversion to the old Garamond
    # stack surfaces in CI.
    assert ".aleph-mark" in css
    aleph_block_start = css.index(".aleph-mark {")
    aleph_block = css[aleph_block_start : aleph_block_start + 400]
    assert "Rubik" in aleph_block, "expected Rubik in the .aleph-mark rule"
