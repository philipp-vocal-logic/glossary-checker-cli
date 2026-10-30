from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_UPPER = r"[A-ZÀ-ÖØ-Þ]"
_LOWER = r"[a-zß-öø-ÿ]"
SUBWORD_PATTERN = re.compile(
    rf"{_UPPER}{{2,}}s(?={_UPPER}{_LOWER}|\d|_|\b)"
    rf"|{_UPPER}+(?={_UPPER}{_LOWER}|\d|_|\b)"
    rf"|{_UPPER}?{_LOWER}+|\d+"
)
INVARIANT_SINGULARS = frozenset(
    {"alias", "atlas", "bias", "canvas", "chaos", "corpus", "lens", "news", "series", "species"}
)
IRREGULAR_PLURALS = {
    "analyses": "analysis",
    "axes": "axis",
    "buses": "bus",
    "children": "child",
    "cookies": "cookie",
    "crises": "crisis",
    "indices": "index",
    "matrices": "matrix",
    "movies": "movie",
    "people": "person",
    "statuses": "status",
    "theses": "thesis",
    "vertices": "vertex",
}
_STOPWORDS = {"a", "an", "by", "for", "from", "in", "of", "on", "that", "the", "to", "who"}


def split_subwords(text: str) -> tuple[str, ...]:
    """Split an identifier or phrase into normalized lowercase sub-words."""
    return tuple(match.group(0).lower() for match in SUBWORD_PATTERN.finditer(text))


def singularize(word: str) -> str:
    """Normalize a lowercase English sub-word to its singular form."""
    if irregular := IRREGULAR_PLURALS.get(word):
        return irregular
    if len(word) <= 3 or word in INVARIANT_SINGULARS:
        return word
    if word.endswith("es") and word[:-2] in INVARIANT_SINGULARS:
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return f"{word[:-3]}y"
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def normalize_subwords(text: str) -> tuple[str, ...]:
    """Split an identifier or phrase into singularized lowercase sub-words."""
    return tuple(singularize(word) for word in split_subwords(text))


@dataclass(frozen=True, slots=True)
class Term:
    """An approved word or phrase defined in the glossary."""

    term: str
    definition: str
    forbidden_terms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Glossary:
    """The configured collection of canonical terms and their definitions for a project."""

    terms: tuple[Term, ...]
    paths: tuple[Path, ...] = (Path("."),)
    exclude: tuple[str, ...] = ()
    similarity_threshold: float = 0.65
    source_path: Path = Path("glossary.toml")

    def forbidden_rules(self) -> list[tuple[tuple[str, ...], str, Term]]:
        """Return normalized subword rules for all configured forbidden_terms."""
        return [
            (norm, forbidden, entry)
            for entry in self.terms
            for forbidden in entry.forbidden_terms
            if (norm := normalize_subwords(forbidden))
        ]


@dataclass(frozen=True, slots=True)
class Finding:
    """A detected problem reported by the checker during validation or file checking."""

    file: Path
    message: str
    suggestion: str
    line: int = 1
    column: int = 1

    def format(self) -> str:
        """Format the finding as a single noise-free diagnostic line."""
        location = f"{self.file}:{self.line}:{self.column}"
        return f"{location}: {self.message} Suggestion: {self.suggestion}"


def _require_str(raw_field: object, field_name: str) -> str:
    if not isinstance(raw_field, str):
        raise ValueError(f"Expected string for '{field_name}'.")
    return raw_field.strip()


def _require_str_tuple(raw_field: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw_field, list) or not all(isinstance(part, str) for part in raw_field):
        raise ValueError(f"Expected list of strings for '{field_name}'.")
    return tuple(part.strip() for part in raw_field)


def _reject_unknown_keys(mapping: dict[str, object], allowed: set[str], section: str) -> None:
    if unknown := sorted(set(mapping) - allowed):
        raise ValueError(f"Unknown key(s) in {section}: {', '.join(unknown)}.")


def _load_term(raw_entry: object) -> Term:
    if not isinstance(raw_entry, dict):
        raise ValueError("Each entry in 'terms' must be a table.")
    _reject_unknown_keys(raw_entry, {"term", "definition", "forbidden_terms"}, "'terms' entry")
    return Term(
        term=_require_str(raw_entry.get("term", ""), "term"),
        definition=_require_str(raw_entry.get("definition", ""), "definition"),
        forbidden_terms=_require_str_tuple(raw_entry.get("forbidden_terms", []), "forbidden_terms"),
    )


def load_glossary(path: Path) -> Glossary:
    """Load a glossary configuration from a TOML file."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    _reject_unknown_keys(raw, {"settings", "terms"}, "glossary configuration")
    settings = raw.get("settings", {})
    raw_terms = raw.get("terms", [])
    if not isinstance(settings, dict) or not isinstance(raw_terms, list):
        raise ValueError("Invalid 'settings' or 'terms' section in glossary configuration.")
    _reject_unknown_keys(settings, {"paths", "exclude", "similarity_threshold"}, "'settings'")

    terms = tuple(_load_term(raw_entry) for raw_entry in raw_terms)
    paths = tuple(
        Path(raw_path) for raw_path in _require_str_tuple(settings.get("paths", ["."]), "paths")
    )
    exclude = _require_str_tuple(settings.get("exclude", []), "exclude")
    raw_threshold = settings.get("similarity_threshold", 0.65)
    if isinstance(raw_threshold, bool) or not isinstance(raw_threshold, (int, float)):
        raise ValueError("Expected number for 'similarity_threshold'.")
    similarity_threshold = float(raw_threshold)
    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("'similarity_threshold' must be between 0.0 and 1.0.")

    return Glossary(
        terms=terms,
        paths=paths,
        exclude=exclude,
        similarity_threshold=similarity_threshold,
        source_path=path,
    )


def _contains_subwords(words: tuple[str, ...], target: tuple[str, ...]) -> bool:
    length = len(target)
    return any(words[index : index + length] == target for index in range(len(words) - length + 1))


def validate_glossary(glossary: Glossary) -> list[Finding]:
    """Validate the glossary for collisions, duplicate meanings, and forbidden_term usage."""
    findings: list[Finding] = []
    source = glossary.source_path

    canonical_by_norm: dict[tuple[str, ...], Term] = {}
    for entry in glossary.terms:
        norm_term = normalize_subwords(entry.term)
        if not norm_term:
            findings.append(
                Finding(
                    file=source,
                    message="Glossary contains an empty term.",
                    suggestion="Provide a non-empty canonical term name.",
                )
            )
            continue

        if not entry.definition:
            findings.append(
                Finding(
                    file=source,
                    message=f"Term '{entry.term}' has an empty definition.",
                    suggestion=f"Provide a clear definition for '{entry.term}'.",
                )
            )

        if norm_term in canonical_by_norm:
            existing = canonical_by_norm[norm_term]
            findings.append(
                Finding(
                    file=source,
                    message=(
                        f"Duplicate canonical term '{entry.term}' "
                        f"(collides with '{existing.term}')."
                    ),
                    suggestion=f"Keep only one canonical term entry for '{existing.term}'.",
                )
            )
        else:
            canonical_by_norm[norm_term] = entry

    forbidden_owner: dict[tuple[str, ...], tuple[str, Term]] = {}
    for norm_forbidden, forbidden, entry in glossary.forbidden_rules():
        for norm_canonical, colliding in canonical_by_norm.items():
            if _contains_subwords(norm_canonical, norm_forbidden):
                findings.append(
                    Finding(
                        file=source,
                        message=(
                            f"Term '{colliding.term}' collides with forbidden_term "
                            f"'{forbidden}' in '{entry.term}'."
                        ),
                        suggestion=(
                            f"Remove '{forbidden}' from forbidden_terms of '{entry.term}' "
                            f"or merge '{colliding.term}' into '{entry.term}'."
                        ),
                    )
                )

        if norm_forbidden in forbidden_owner:
            prev_raw, prev_entry = forbidden_owner[norm_forbidden]
            findings.append(
                Finding(
                    file=source,
                    message=(
                        f"Forbidden term '{forbidden}' in '{entry.term}' collides with "
                        f"'{prev_raw}' in '{prev_entry.term}'."
                    ),
                    suggestion=(
                        f"Keep '{forbidden}' under only one canonical term so each "
                        "forbidden_term maps to a single canonical term."
                    ),
                )
            )
        else:
            forbidden_owner[norm_forbidden] = (forbidden, entry)

    findings.extend(_check_definition_similarity(glossary))
    findings.extend(_check_definitions_for_forbidden_terms(glossary, forbidden_owner))
    return findings


def _definition_words(definition: str) -> frozenset[str]:
    return frozenset(word for word in normalize_subwords(definition) if word not in _STOPWORDS)


def _check_definition_similarity(glossary: Glossary) -> list[Finding]:
    normalized_defs = [
        (entry, words) for entry in glossary.terms if (words := _definition_words(entry.definition))
    ]
    return [
        Finding(
            file=glossary.source_path,
            message=(
                f"Terms '{entry_a.term}' and '{entry_b.term}' have overlapping "
                f"definitions (similarity: {ratio:.2f})."
            ),
            suggestion=(
                f"Merge '{entry_b.term}' into forbidden_terms of '{entry_a.term}' "
                "or sharpen their definitions to distinguish their meanings."
            ),
        )
        for index, (entry_a, words_a) in enumerate(normalized_defs)
        for entry_b, words_b in normalized_defs[index + 1 :]
        if (ratio := len(words_a & words_b) / len(words_a | words_b))
        >= glossary.similarity_threshold
    ]


def _check_definitions_for_forbidden_terms(
    glossary: Glossary,
    forbidden_owner: dict[tuple[str, ...], tuple[str, Term]],
) -> list[Finding]:
    return [
        Finding(
            file=glossary.source_path,
            message=f"Definition of '{entry.term}' uses forbidden_term '{raw_forbidden}'.",
            suggestion=f"Use canonical term '{canonical.term}' ({canonical.definition}).",
        )
        for entry in glossary.terms
        if (words := normalize_subwords(entry.definition))
        for forbidden_words, (raw_forbidden, canonical) in forbidden_owner.items()
        if _contains_subwords(words, forbidden_words)
    ]
