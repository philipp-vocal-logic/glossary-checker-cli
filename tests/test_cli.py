from pathlib import Path

import pytest

from glossary_checker_cli.cli import main


def test_main_returns_zero_when_no_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer of goods."\n'
        'forbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    (tmp_path / "clean.py").write_text("customer_id = 42\n", encoding="utf-8")

    exit_code = main(["--config", str(config)])
    assert exit_code == 0 and capsys.readouterr().out == ""


def test_main_discovers_parent_glossary_from_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer of goods."\n'
        'forbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    sub_dir = tmp_path / "src" / "pkg"
    sub_dir.mkdir(parents=True)
    (sub_dir / "clean.py").write_text("customer_id = 42\n", encoding="utf-8")

    monkeypatch.chdir(sub_dir)
    assert main([]) == 0 and capsys.readouterr().out == ""


def test_main_returns_two_when_default_config_not_in_any_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2 and "Failed to load glossary configuration" in capsys.readouterr().err


def test_main_returns_one_and_prints_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer of goods."\n'
        'forbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    (tmp_path / "active.py").write_text("client_id = 42\n", encoding="utf-8")

    exit_code = main(["--config", str(config)])
    assert exit_code == 1 and "active.py:1:1:" in capsys.readouterr().out


def test_main_returns_two_when_config_file_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.toml"
    exit_code = main(["--config", str(missing)])
    assert exit_code == 2 and "Failed to load glossary configuration" in capsys.readouterr().err


def test_main_returns_two_when_config_schema_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text('[settings]\nsimilarity_threshold = "high"\n', encoding="utf-8")
    exit_code = main(["--config", str(config)])
    assert exit_code == 2 and "Expected number" in capsys.readouterr().err


def test_main_filters_to_positional_target_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer of goods."\n'
        'forbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    clean_file = tmp_path / "clean.py"
    dirty_file = tmp_path / "dirty.py"
    clean_file.write_text("customer_id = 42\n", encoding="utf-8")
    dirty_file.write_text("client_id = 42\n", encoding="utf-8")

    assert main(["--config", str(config), str(clean_file)]) == 0
    assert main(["--config", str(config), str(dirty_file)]) == 1
    assert "dirty.py:1:1:" in capsys.readouterr().out
