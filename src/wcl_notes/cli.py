"""Command-line MVP: report code + fight + player -> MRT note in the terminal."""

import argparse
import sys

from wcl_notes import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wcl_notes.cli",
        description="Génère une note MRT / NSRT à partir d'un log Warcraft Logs.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
