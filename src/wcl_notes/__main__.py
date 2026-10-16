"""Entry point: ``python -m wcl_notes`` launches the desktop app."""

import sys


def main() -> int:
    from wcl_notes.ui.app import main as run_app

    return run_app()


if __name__ == "__main__":
    sys.exit(main())
