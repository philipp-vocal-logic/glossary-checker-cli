from pathlib import Path

import pytest

from glossary_checker_cli.core import (
    Finding,
    Glossary,
    Term,
    load_glossary,
    normalize_subwords,
    singularize,
    split_subwords,
    validate_glossary,
)


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        pytest.param("clients", "client", id="regular_plural_s"),
        pytest.param("categories", "category", id="ies_to_y"),
        pytest.param("pies", "pie", id="short_ies_strips_s_only"),
        pytest.param("boxes", "box", id="xes_to_x"),
        pytest.param("classes", "class", id="sses_to_ss"),
        pytest.param("matches", "match", id="ches_to_ch"),
        pytest.param("dishes", "dish", id="shes_to_sh"),
        pytest.param("buzzes", "buzz", id="zes_to_z"),
        pytest.param("status", "status", id="us_ending_unchanged"),
        pytest.param("analysis", "analysis", id="is_ending_unchanged"),
        pytest.param("class", "class", id="ss_ending_unchanged"),
        pytest.param("bus", "bus", id="three_letter_word_unchanged"),
        pytest.param("lens", "lens", id="invariant_singular_unchanged"),
        pytest.param("lenses", "lens", id="invariant_plural_es_stripped"),
        pytest.param("alias", "alias", id="alias_singular_unchanged"),
        pytest.param("aliases", "alias", id="aliases_plural_to_alias"),
    ],
)
def test_singularize(word: str, expected: str) -> None:
    assert singularize(word) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("snake_case_name", ("snake", "case", "name"), id="snake_case"),
        pytest.param("camelCaseName", ("camel", "case", "name"), id="camel_case"),
        pytest.param("PascalCaseName", ("pascal", "case", "name"), id="pascal_case"),
        pytest.param("UPPER_SNAKE_CASE", ("upper", "snake", "case"), id="upper_snake_case"),
        pytest.param("HTTPRequest2", ("http", "request", "2"), id="acronym_and_digits"),
        pytest.param("kebab-case-name", ("kebab", "case", "name"), id="kebab_case"),
        pytest.param("Plain prose words", ("plain", "prose", "words"), id="prose"),
        pytest.param("Kündigung_client", ("kündigung", "client"), id="unicode_subwords"),
        pytest.param("___", (), id="only_delimiters"),
    ],
)
def test_split_subwords(text: str, expected: tuple[str, ...]) -> None:
    assert split_subwords(text) == expected


def test_normalize_subwords_splits_and_singularizes() -> None:
    assert normalize_subwords("clientProfiles") == ("client", "profile")


def test_finding_format_returns_diagnostic_line() -> None:
    finding = Finding(
        file=Path("src/app.py"),
        line=10,
        column=4,
        message="Forbidden term 'client' found in 'client_id'.",
        suggestion="Use canonical term 'customer'.",
    )
    assert finding.format() == (
        "src/app.py:10:4: Forbidden term 'client' found in 'client_id'. "
        "Suggestion: Use canonical term 'customer'."
    )


def test_glossary_forbidden_rules_skips_empty_entries() -> None:
    term = Term(
        term="customer",
        definition="Buyer of goods.",
        forbidden_terms=("client_profiles", "___"),
    )
    glossary = Glossary(terms=(term,))
    assert glossary.forbidden_rules() == [
        (("client", "profile"), "client_profiles", term),
    ]


def test_validate_glossary_accepts_valid_glossary() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="An entity that purchases goods from the platform.",
                forbidden_terms=("client",),
            ),
            Term(
                term="invoice",
                definition="A billing statement issued after checkout.",
            ),
        )
    )
    assert validate_glossary(glossary) == []


def test_validate_glossary_detects_empty_term() -> None:
    glossary = Glossary(
        terms=(Term(term="   ", definition="A blank term entry."),),
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Glossary contains an empty term.",
            suggestion="Provide a non-empty canonical term name.",
        )
    ]


def test_validate_glossary_detects_empty_definition() -> None:
    glossary = Glossary(
        terms=(Term(term="customer", definition=""),),
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Term 'customer' has an empty definition.",
            suggestion="Provide a clear definition for 'customer'.",
        )
    ]


def test_validate_glossary_detects_duplicate_canonical_term() -> None:
    glossary = Glossary(
        terms=(
            Term(term="customer", definition="First definition of customer."),
            Term(term="customers", definition="Unrelated second entry."),
        )
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Duplicate canonical term 'customers' (collides with 'customer').",
            suggestion="Keep only one canonical term entry for 'customer'.",
        )
    ]


def test_validate_glossary_detects_term_and_forbidden_collision() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="An entity that purchases goods from the platform.",
                forbidden_terms=("buyer",),
            ),
            Term(
                term="buyer",
                definition="A person executing a purchase order.",
            ),
        )
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Term 'buyer' collides with forbidden_term 'buyer' in 'customer'.",
            suggestion=(
                "Remove 'buyer' from forbidden_terms of 'customer' "
                "or merge 'buyer' into 'customer'."
            ),
        )
    ]


def test_validate_glossary_detects_shared_forbidden_term() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="An entity that purchases goods from the platform.",
                forbidden_terms=("client",),
            ),
            Term(
                term="merchant",
                definition="A business offering products in the storefront.",
                forbidden_terms=("client",),
            ),
        )
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Forbidden term 'client' in 'merchant' collides with 'client' in 'customer'.",
            suggestion=(
                "Keep 'client' under only one canonical term so each "
                "forbidden_term maps to a single canonical term."
            ),
        )
    ]


def test_validate_glossary_detects_overlapping_definitions() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="A registered person who buys items from the online store.",
            ),
            Term(
                term="shopper",
                definition="A registered person who buys products from the online store.",
            ),
        ),
        similarity_threshold=0.65,
    )
    findings = validate_glossary(glossary)
    assert len(findings) == 1 and "overlapping definitions" in findings[0].message


def test_validate_glossary_detects_forbidden_term_inside_definition() -> None:
    glossary = Glossary(
        terms=(
            Term(
                term="customer",
                definition="An entity that purchases goods from the platform.",
                forbidden_terms=("client",),
            ),
            Term(
                term="invoice",
                definition="A billing statement sent to a client after checkout.",
            ),
        )
    )
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Definition of 'invoice' uses forbidden_term 'client'.",
            suggestion=(
                "Use canonical term 'customer' (An entity that purchases goods from the platform.)."
            ),
        )
    ]


def test_load_glossary_parses_toml(tmp_path: Path) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(
        '[settings]\npaths = ["src"]\nexclude = ["build/"]\nsimilarity_threshold = 0.7\n\n'
        '[[terms]]\nterm = "customer"\ndefinition = "Buyer of goods."\n'
        'forbidden_terms = ["client"]\n',
        encoding="utf-8",
    )
    assert load_glossary(config) == Glossary(
        terms=(
            Term(
                term="customer",
                definition="Buyer of goods.",
                forbidden_terms=("client",),
            ),
        ),
        paths=(Path("src"),),
        exclude=("build/",),
        similarity_threshold=0.7,
        source_path=config,
    )


@pytest.mark.parametrize(
    ("raw_toml", "expected_message"),
    [
        ('settings = "bad"\n', "Invalid 'settings'"),
        ('terms = ["bad"]\n', "must be a table"),
        ("[[terms]]\nterm = 5\n", "Expected string for 'term'"),
        ('[[terms]]\nterm = "a"\nforbidden_terms = "client"\n', "Expected list of strings"),
        ('[settings]\nsimilarity_threshold = "high"\n', "Expected number"),
        ("[settings]\nsimilarity_threshold = true\n", "Expected number"),
        ("[settings]\nsimilarity_threshold = 1.5\n", "must be between 0.0 and 1.0"),
    ],
)
def test_load_glossary_rejects_invalid_schema(
    tmp_path: Path, raw_toml: str, expected_message: str
) -> None:
    config = tmp_path / "glossary.toml"
    config.write_text(raw_toml, encoding="utf-8")
    with pytest.raises(ValueError, match=expected_message):
        load_glossary(config)
