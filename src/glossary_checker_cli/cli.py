from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

from glossary_checker_cli.checker import check
from glossary_checker_cli.core import load_glossary


def _resolve_config_path(config: Path) -> Path:
    if config != Path("glossary.toml") or config.is_file():
        return config
    for parent in Path.cwd().resolve().parents:
        candidate = parent / "glossary.toml"
        if candidate.is_file():
            return candidate
    return config


def main(argv: Sequence[str] | None = None) -> int:
    """Run the glossary checker CLI."""
    parser = argparse.ArgumentParser(
        prog="glossary",
        description="Validate glossary terms and inspect configured target_files for findings.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Optional target_files or directories to check.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("glossary.toml"),
        help="Path to the glossary configuration file (default: glossary.toml).",
    )
    args = parser.parse_args(argv)
    config_path = _resolve_config_path(args.config)

    try:
        glossary = load_glossary(config_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        print(f"{config_path}:1:1: Failed to load glossary configuration: {error}", file=sys.stderr)
        return 2

    findings = check(glossary, targets=tuple(args.files) or None)
    for finding in findings:
        print(finding.format())

    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
