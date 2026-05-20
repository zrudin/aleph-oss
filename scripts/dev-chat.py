"""Send a single chat turn to a local pa dev server and print the result.

Use this from an automated session to drive an end-to-end conversation against
a running dev server (typically started with throwaway PA_VAULT_PATH and a
non-default PA_PORT — see CLAUDE.md "Self-testing").

Each invocation is one user turn. To continue an existing thread, pass
`--thread <id>` (the script prints the thread id from the first turn).

Examples:
    # Start a fresh thread
    uv run python scripts/dev-chat.py "hi"

    # Continue the thread
    uv run python scripts/dev-chat.py --thread <id> "what did I just say?"

    # Talk to a non-default port
    uv run python scripts/dev-chat.py --base http://127.0.0.1:8766 "hi"

Output is a digest of one turn: thread id, generated title (if any), every
tool call the model made with arguments + result preview, and the full
assistant text. Exits non-zero if the SSE stream emitted an `error` event.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin

import httpx


def send(message: str, thread_id: str | None, base: str, timeout: float) -> dict:
    url = urljoin(base, "/chat")
    payload: dict = {"message": message}
    if thread_id:
        payload["thread_id"] = thread_id

    assistant_chunks: list[str] = []
    tool_calls: list[dict] = []
    thread = thread_id
    title: str | None = None
    error: str | None = None

    with httpx.stream("POST", url, json=payload, timeout=timeout) as resp:
        if resp.status_code != 200:
            raise SystemExit(f"chat failed: HTTP {resp.status_code} — {resp.read()!r}")
        for raw in resp.iter_lines():
            if not raw.startswith("data: "):
                continue
            try:
                event = json.loads(raw[len("data: ") :])
            except json.JSONDecodeError:
                continue
            kind = event.get("kind")
            if kind == "thread":
                thread = event.get("text")
            elif kind == "token":
                assistant_chunks.append(event.get("text") or "")
            elif kind == "tool_start":
                tool_calls.append({
                    "name": (event.get("tool") or {}).get("name"),
                    "args": (event.get("tool") or {}).get("arguments"),
                    "result_preview": None,
                    "ok": None,
                })
            elif kind == "tool_result":
                if tool_calls:
                    text = event.get("text") or ""
                    tool_calls[-1]["result_preview"] = text[:280]
                    tool_calls[-1]["ok"] = (event.get("tool") or {}).get("ok")
            elif kind == "title":
                title = event.get("text")
            elif kind == "error":
                error = event.get("text")
            elif kind == "done":
                break

    return {
        "thread_id": thread,
        "title": title,
        "assistant": "".join(assistant_chunks),
        "tool_calls": tool_calls,
        "error": error,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("message", help="the user turn to send")
    ap.add_argument("--thread", default=None, help="continue an existing thread id")
    ap.add_argument("--base", default="http://127.0.0.1:8766", help="dev server base URL")
    ap.add_argument("--timeout", type=float, default=600.0, help="per-request timeout in seconds")
    args = ap.parse_args()

    result = send(args.message, args.thread, args.base, args.timeout)
    print(f"thread_id: {result['thread_id']}")
    if result["title"]:
        print(f"title: {result['title']}")
    if result["tool_calls"]:
        print(f"tool_calls ({len(result['tool_calls'])}):")
        for tc in result["tool_calls"]:
            print(f"  - {tc['name']} ok={tc['ok']} args={json.dumps(tc['args'])[:160]}")
            if tc["result_preview"]:
                preview = tc["result_preview"].replace("\n", " ⏎ ")
                print(f"      → {preview}")
    print("---")
    print(result["assistant"])
    if result["error"]:
        print(f"\n[ERROR EVENT] {result['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
