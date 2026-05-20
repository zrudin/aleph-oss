# Security policy

## Reporting a vulnerability

Please report vulnerabilities **privately**, not via a public issue.

- Preferred: open a [GitHub Security Advisory](https://github.com/zrudin/aleph-oss/security/advisories/new).
- Alternative: email `8495848+zrudin@users.noreply.github.com`.

This project is maintained by a single person on a best-effort basis. There
is no formal SLA — expect a reply within a week or two, and longer for
substantive fixes.

## Threat model

aleph is a **local-first, single-user** assistant. The intended deployment is
one person running it on their own laptop. The security model reflects that:

- The FastAPI server binds to **loopback only** (`127.0.0.1`). It is not
  meant to be exposed to a LAN, hosted publicly, or run in a multi-tenant
  context. If you do any of those things, the protections below are
  insufficient and you are on your own.
- All user data lives in an **encrypted sparsebundle vault** mounted on
  demand. The app refuses to start if the vault is not mounted.
- External connectors (web search, Notion, etc.) are **opt-in and
  fail-closed**: each group must be both configured at startup *and*
  toggled on by the user before the model can call its tools.
- Connector credentials and the vault passphrase are stored in the macOS
  **Keychain** (service `pa`), not on disk.
- Outbound HTTP goes through a hardened client (`src/pa/net.py`) that
  disables proxies/cookies, caps response size, rejects non-http(s)
  schemes, and refuses any host that resolves to a private, loopback, or
  link-local address — to prevent the model from being tricked into
  scanning the LAN or hitting our own loopback services.
- Vault file writes go through `VaultManager.resolve_inside()`, which
  rejects absolute paths, `~`-prefixed paths, and anything that escapes
  the vault root.

## Out of scope

- Multi-user deployments, network exposure, container/cloud hosting.
- Adversarial models running locally (you control which model is loaded).
- Physical access to an unlocked laptop with the vault mounted.
