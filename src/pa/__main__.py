"""Entry point: `python -m pa` starts the FastAPI server."""

from __future__ import annotations

import sys

import uvicorn

from pa.config import settings
from pa.vault.manager import VaultNotMountedError, get_vault


def main() -> None:
    # Fail fast if the vault isn't mounted — much better than a 500-page wall
    # of tracebacks two minutes into the first chat turn.
    try:
        get_vault().ensure_mounted()
    except VaultNotMountedError as exc:
        sys.stderr.write(f"\nERROR: {exc}\n\n")
        sys.stderr.write("Mount the vault with `make vault-mount`, then retry.\n")
        sys.exit(2)

    uvicorn.run(
        "pa.server:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
