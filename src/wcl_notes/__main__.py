"""Entry point: ``python -m wcl_notes`` launches the desktop app."""

import sys
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--self-check":
        from wcl_notes.ui.self_check import run_self_check

        return run_self_check(Path(args[1]))

    from wcl_notes.ui.app import main as run_app

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
