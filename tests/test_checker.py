from pathlib import Path

import pytest

from glossary_checker_cli.checker import check, check_text
from glossary_checker_cli.core import Finding, Glossary, Term


def _sample_glossary(
    *,
    source_path: Path = Path("glossary.toml"),
    paths: tuple[Path, ...] = (Path("."),),
    exclude: tuple[str, ...] = (),
) -> Glossary:
    return Glossary(
        terms=(
            Term(
                term="customer",
                definition="An entity that purchases goods from the platform.",
                forbidden_terms=("client", "buyer_profile"),
            ),
        ),
        paths=paths,
        exclude=exclude,
        source_path=source_path,
    )


@pytest.mark.parametrize(
    ("sample", "expected_column", "expected_forbidden", "expected_context"),
    [
        pytest.param(
            "def fetch_client():\n",
            11,
            "client",
            "fetch_client",
            id="snake_case_subword",
        ),
        pytest.param(
            "record = buyerProfile\n",
            10,
            "buyer_profile",
            "buyerProfile",
            id="camel_case_phrase",
        ),
        pytest.param(
            "# Update the buyer profile record\n",
            14,
            "buyer_profile",
            "buyer profile",
            id="space_separated_phrase",
        ),
        pytest.param(
            "return buyer_profile\n",
            8,
            "buyer_profile",
            "buyer_profile",
            id="exact_identifier",
        ),
        pytest.param(
            "items = buyer_profiles\n",
            9,
            "buyer_profile",
            "buyer_profiles",
            id="plural_phrase",
        ),
    ],
)
def test_check_text_detects_forbidden_term_occurrence(
    sample: str,
    expected_column: int,
    expected_forbidden: str,
    expected_context: str,
) -> None:
    findings = check_text(sample, _sample_glossary(), file=Path("sample.py"))
    assert findings == [
        Finding(
            file=Path("sample.py"),
            line=1,
            column=expected_column,
            message=f"Forbidden term '{expected_forbidden}' found in '{expected_context}'.",
            suggestion=(
                "Use canonical term 'customer' (An entity that purchases goods from the platform.)."
            ),
        )
    ]


def test_check_text_sorts_findings_by_column_order() -> None:
    sample = "records = [buyer_profiles, fetch_clients()]\n"
    findings = check_text(sample, _sample_glossary(), file=Path("sample.py"))
    assert [finding.column for finding in findings] == [12, 34]


def test_check_text_does_not_match_across_punctuation() -> None:
    findings = check_text("items = [buyer, profile]\n", _sample_glossary(), file=Path("sample.py"))
    assert findings == []


def test_check_text_returns_empty_when_no_forbidden_rules() -> None:
    glossary = Glossary(
        terms=(Term(term="customer", definition="Buyer of goods."),),
    )
    assert check_text("client = 1\n", glossary, file=Path("sample.py")) == []


def test_check_excludes_paths_matched_by_gitignore_and_git_exclude(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignored_dir/\n", encoding="utf-8")
    (tmp_path / "ignored_dir").mkdir()
    (tmp_path / "ignored_dir" / "skip.py").write_text("client = 1\n", encoding="utf-8")
    git_meta_dir = tmp_path / ".git" / "info"
    git_meta_dir.mkdir(parents=True)
    (git_meta_dir / "exclude").write_text("local_ignore.py\n", encoding="utf-8")
    (tmp_path / "local_ignore.py").write_text("client = 2\n", encoding="utf-8")

    glossary = _sample_glossary(source_path=tmp_path / "glossary.toml")
    assert check(glossary) == []


def test_check_excludes_paths_matched_by_config_exclude_even_when_explicit(tmp_path: Path) -> None:
    skip_file = tmp_path / "skip.py"
    skip_file.write_text("client = 1\n", encoding="utf-8")

    glossary = _sample_glossary(
        source_path=tmp_path / "glossary.toml",
        exclude=("skip.py",),
    )
    assert check(glossary) == []
    assert check(glossary, targets=[skip_file]) == []


def test_check_evaluates_configured_file_path_and_reports_missing_configured_path(
    tmp_path: Path,
) -> None:
    target = tmp_path / "active.py"
    target.write_text("client_id = 42\n", encoding="utf-8")

    glossary = _sample_glossary(
        source_path=tmp_path / "glossary.toml",
        paths=(Path("active.py"), Path("missing.py")),
    )
    findings = check(glossary)
    assert [finding.file for finding in findings] == [Path("active.py"), Path("missing.py")]
    assert "does not exist" in findings[1].message


def test_check_skips_binary_files_and_reports_non_utf8_files(tmp_path: Path) -> None:
    (tmp_path / "binary.bin").write_bytes(b"client\x00data")
    (tmp_path / "invalid.txt").write_bytes(b"\xff\xfeclient")

    glossary = _sample_glossary(source_path=tmp_path / "glossary.toml")
    findings = check(glossary)
    assert len(findings) == 1
    assert findings[0].file == Path("invalid.txt")
    assert "Failed to read UTF-8 target_file" in findings[0].message


def test_check_text_respects_inline_ignore_comments() -> None:
    sample = (
        "client_id = 1  # glossary: ignore\n"
        "record = fetch_client(buyer_profile)  # glossary: ignore[client]\n"
        "active = client_id  # glossary: ignore[buyer_profile]\n"
        'note = "see glossary: ignore"; client_id = 2\n'
        "empty_brackets = client_id  # glossary: ignore[]\n"
    )
    findings = check_text(sample, _sample_glossary(), file=Path("sample.py"))
    assert [(finding.line, finding.column) for finding in findings] == [
        (2, 23),
        (3, 10),
        (4, 32),
        (5, 18),
    ]


def test_check_text_handles_unicode_and_plural_acronyms() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="Buyer of goods.",
                forbidden_terms=("client", "Kunde", "id"),
            ),
        ),
    )
    sample = "entry = Kündigung_client\nkunde = 1\nrecords = userIDs\n"
    findings = check_text(sample, glossary, file=Path("sample.py"))
    assert [finding.message for finding in findings] == [
        "Forbidden term 'client' found in 'Kündigung_client'.",
        "Forbidden term 'Kunde' found in 'kunde'.",
        "Forbidden term 'id' found in 'userIDs'.",
    ]


def test_check_excludes_git_dir_and_config_file_by_default_and_when_explicit(
    tmp_path: Path,
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer."\nforbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    git_msg = git_dir / "COMMIT_EDITMSG"
    git_msg.write_text("fix client issue\n", encoding="utf-8")

    glossary = _sample_glossary(source_path=config, exclude=())
    assert check(glossary) == []
    assert check(glossary, targets=[config, git_msg]) == []


def test_check_supports_symlinked_config_outside_base_dir(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    real_config = shared_dir / "company_glossary.toml"
    real_config.write_text(
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer."\nforbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    symlink_config = repo_dir / "glossary.toml"
    symlink_config.symlink_to(real_config)
    (repo_dir / "app.py").write_text("client_id = 1\n", encoding="utf-8")

    glossary = _sample_glossary(source_path=symlink_config)
    assert [finding.file for finding in check(glossary)] == [Path("app.py")]


def test_check_reports_missing_explicit_target_path(tmp_path: Path) -> None:
    glossary = _sample_glossary(source_path=tmp_path / "glossary.toml")
    findings = check(glossary, targets=[Path("nonexistent.py")])
    assert len(findings) == 1 and "does not exist" in findings[0].message


def test_check_handles_configured_paths_outside_base_dir(tmp_path: Path) -> None:
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / ".git").mkdir()
    (outside_dir / ".git" / "config").write_text("client = 1\n", encoding="utf-8")
    (outside_dir / "file.py").write_text("client_id = 1\n", encoding="utf-8")

    glossary = _sample_glossary(
        source_path=sub_dir / "glossary.toml",
        paths=(Path("../outside"),),
    )
    findings = check(glossary)
    assert [finding.file for finding in findings] == [Path("../outside/file.py")]


def test_check_resolves_explicit_targets_from_cwd_and_base_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_dir = tmp_path / "root"
    sub_dir = base_dir / "sub"
    sub_dir.mkdir(parents=True)
    (base_dir / "app.py").write_text("client_id = 1\n", encoding="utf-8")
    (sub_dir / "app.py").write_text("customer_id = 1\n", encoding="utf-8")
    (base_dir / "only_in_base.py").write_text("client_id = 2\n", encoding="utf-8")

    glossary = _sample_glossary(source_path=base_dir / "glossary.toml")
    monkeypatch.chdir(sub_dir)
    assert check(glossary, targets=[Path("app.py")]) == []
    assert [finding.file for finding in check(glossary, targets=[Path("only_in_base.py")])] == [
        Path("only_in_base.py")
    ]


def test_check_text_preserves_line_numbers_across_form_feed_and_unicode_separators() -> None:
    sample = "header = 'page\x0cbreak\u2028here'\r\nclient_id = 1\n"
    findings = check_text(sample, _sample_glossary(), file=Path("sample.py"))
    assert [(finding.line, finding.column) for finding in findings] == [(2, 1)]


def test_check_handles_non_utf8_gitignore_and_git_exclude(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes(b"# \xff\xfe comment\nignored.py\n")
    (tmp_path / "ignored.py").write_text("client = 1\n", encoding="utf-8")
    git_meta_dir = tmp_path / ".git" / "info"
    git_meta_dir.mkdir(parents=True)
    (git_meta_dir / "exclude").write_bytes(b"# \xff\xfe comment\nlocal_ignore.py\n")
    (tmp_path / "local_ignore.py").write_text("client = 2\n", encoding="utf-8")

    glossary = _sample_glossary(source_path=tmp_path / "glossary.toml")
    findings = check(glossary)
    assert [finding.file for finding in findings] == [Path(".gitignore")]
    assert "Failed to read UTF-8 target_file" in findings[0].message
