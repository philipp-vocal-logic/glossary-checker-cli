from pathlib import Path

import archcheck
import pytest
from symbol_checker.checker import check_project
from symbol_checker.schema import load_schema

from glossary_checker_cli.checker import check
from glossary_checker_cli.core import load_glossary


@pytest.mark.integration
def test_project_adheres_to_own_glossary() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    glossary = load_glossary(repo_root / "glossary.toml")
    findings = check(glossary)
    formatted = "\n".join(finding.format() for finding in findings)
    assert not findings, f"Self-check found glossary problems:\n{formatted}"


@pytest.mark.integration
def test_project_adheres_to_own_symbols() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    schema = load_schema(repo_root / "symbols.toml")
    findings = check_project(schema, root=repo_root)
    formatted = "\n".join(finding.format_line() for finding in findings)
    assert not findings, f"Self-check found symbol problems:\n{formatted}"


@pytest.mark.integration
def test_project_adheres_to_own_architecture() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    assert archcheck.main(["--config", str(repo_root / "arch.toml")]) == 0
