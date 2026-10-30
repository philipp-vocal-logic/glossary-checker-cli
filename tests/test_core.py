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
        ("clients", "client"),
        ("categories", "category"),
        ("pies", "pie"),
        ("cookies", "cookie"),
        ("movies", "movie"),
        ("boxes", "box"),
        ("classes", "class"),
        ("matches", "match"),
        ("dishes", "dish"),
        ("buzzes", "buzz"),
        ("status", "status"),
        ("statuses", "status"),
        ("analysis", "analysis"),
        ("analyses", "analysis"),
        ("indices", "index"),
        ("axes", "axis"),
        ("children", "child"),
        ("class", "class"),
        ("bus", "bus"),
        ("buses", "bus"),
        ("lens", "lens"),
        ("lenses", "lens"),
        ("alias", "alias"),
        ("aliases", "alias"),
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
            Term("customer", "An entity that purchases goods from the platform.", ("client",)),
            Term("invoice", "A billing statement issued after checkout."),
        )
    )
    assert validate_glossary(glossary) == []


def test_validate_glossary_detects_empty_term() -> None:
    glossary = Glossary(terms=(Term("   ", "A blank term entry."),))
    assert validate_glossary(glossary) == [
        Finding(
            file=Path("glossary.toml"),
            message="Glossary contains an empty term.",
            suggestion="Provide a non-empty canonical term name.",
        )
    ]


def test_validate_glossary_detects_empty_definition() -> None:
    glossary = Glossary(terms=(Term("customer", ""),))
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
            Term("customer", "First definition of customer."),
            Term("customers", "Unrelated second entry."),
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
            Term("customer_account", "A billing record for a customer.", ("buyer", "account")),
            Term("buyer", "A person executing a purchase order."),
        )
    )
    assert [finding.message for finding in validate_glossary(glossary)] == [
        "Term 'buyer' collides with forbidden_term 'buyer' in 'customer_account'.",
        "Term 'customer_account' collides with forbidden_term 'account' in 'customer_account'.",
    ]


def test_validate_glossary_detects_shared_forbidden_term() -> None:
    glossary = Glossary(
        terms=(
            Term("customer", "An entity that purchases goods from the platform.", ("client",)),
            Term("merchant", "A business offering products in the storefront.", ("client",)),
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
            Term("customer", "A registered person who buys items from the online store."),
            Term("shopper", "A registered person who buys products from the online store."),
            Term("courier", "A registered person who delivers parcels from the local depot."),
        ),
        similarity_threshold=0.65,
    )
    findings = validate_glossary(glossary)
    assert [finding.message for finding in findings] == [
        "Terms 'customer' and 'shopper' have overlapping definitions (similarity: 0.71)."
    ]


def test_validate_glossary_detects_forbidden_term_inside_definition() -> None:
    glossary = Glossary(
        terms=(
            Term("customer", "An entity that purchases goods from the platform.", ("client",)),
            Term("invoice", "A billing statement sent to a client after checkout."),
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
        ("unknown = 1\n", "Unknown key"),
        ("[settings]\nexlude = []\n", "Unknown key"),
        ('[[terms]]\nterm = "a"\nforbidden_term = []\n', "Unknown key"),
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
