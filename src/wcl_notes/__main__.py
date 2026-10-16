"""Entry point: ``python -m wcl_notes`` launches the desktop app."""

import sys


def main() -> int:
    # The Qt interface arrives in roadmap step 3; the CLI is the MVP.
    print("Interface pas encore disponible. Utilisez : uv run python -m wcl_notes.cli")
    return 1


if __name__ == "__main__":
    sys.exit(main())
