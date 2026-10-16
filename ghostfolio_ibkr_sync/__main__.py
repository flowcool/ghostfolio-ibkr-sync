"""Command line entry: `python -m ghostfolio_ibkr_sync` runs one sync."""

import logging
import os
import sys

from ghostfolio_ibkr_sync.app import main
from ghostfolio_ibkr_sync.notify import NOTIFY_WORKER_FLAG, notify_worker


def run() -> int:
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # urllib3 logs full request lines (incl. the IBKR token query param) at DEBUG.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if sys.argv[1:] == [NOTIFY_WORKER_FLAG]:
        return notify_worker()
    return main()


if __name__ == "__main__":
    sys.exit(run())
