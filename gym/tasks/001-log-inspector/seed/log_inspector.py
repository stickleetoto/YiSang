from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def analyze_lines(lines: Iterable[str]) -> dict[str, object]:
    """Return deterministic severity counts and repeated error messages."""
    raise NotImplementedError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="log-inspector")
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
