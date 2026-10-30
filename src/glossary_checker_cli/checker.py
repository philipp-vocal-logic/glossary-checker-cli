from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pathspec

from glossary_checker_cli.core import (
    SUBWORD_PATTERN,
    Finding,
    Glossary,
    Term,
    normalize_subwords,
    singularize,
    validate_glossary,
)

TOKEN_PATTERN = re.compile(r"\w+(?:-\w+)*")
IGNORE_PATTERN = re.compile(
    r"(?:#|//|--|/\*|<!--)\s*glossary:\s*ignore(?:\[([^\]]*)\])?\s*(?:\*/|-->)?\s*$"
)


@dataclass(frozen=True, slots=True)
class _SubwordSpan:
    word: str
    start: int
    end: int
    token_start: int
    token_end: int


def check(glossary: Glossary, targets: Sequence[Path] | None = None) -> list[Finding]:
    """Validate the glossary and inspect all configured target_files for findings."""
    findings = validate_glossary(glossary)
    base_dir = glossary.source_path.parent.resolve()
    roots, target_findings = _resolve_search_roots(base_dir, glossary.paths, targets)
    findings.extend(target_findings)

    ignore_matcher = _build_ignore_matcher(base_dir, glossary.exclude, glossary.source_path)
    rules = glossary.forbidden_rules()
    for target_file in _discover_target_files(base_dir, roots, ignore_matcher):
        content = _read_text_file(target_file)
        if content is not None:
            display_path = (
                target_file.relative_to(base_dir)
                if target_file.is_relative_to(base_dir)
                else Path(os.path.relpath(target_file, base_dir))
            )
            findings.extend(_check_text_with_rules(content, rules, file=display_path))

    return sorted(findings, key=_finding_sort_key)


def check_text(text: str, glossary: Glossary, file: Path) -> list[Finding]:
    """Inspect a text string for any forbidden_term defined in the glossary."""
    return _check_text_with_rules(text, glossary.forbidden_rules(), file=file)


def _check_text_with_rules(
    text: str, rules: list[tuple[tuple[str, ...], str, Term]], file: Path
) -> list[Finding]:
    if not rules:
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        active_line, ignored_norms = _extract_active_line(line)
        if ignored_norms is None:
            continue
        spans = _extract_line_subwords(active_line)
        if spans:
            findings.extend(
                _check_line_spans(active_line, line_number, spans, rules, ignored_norms, file)
            )

    return sorted(findings, key=_finding_sort_key)


def _check_line_spans(
    line: str,
    line_number: int,
    spans: list[_SubwordSpan],
    rules: list[tuple[tuple[str, ...], str, Term]],
    ignored_norms: set[tuple[str, ...]],
    file: Path,
) -> list[Finding]:
    findings: list[Finding] = []
    for forbidden_words, raw_forbidden, entry in rules:
        if forbidden_words in ignored_norms:
            continue
        length = len(forbidden_words)
        for index in range(len(spans) - length + 1):
            window = spans[index : index + length]
            if not _matches_window(line, window, forbidden_words):
                continue
            first, last = window[0], window[-1]
            context = (
                line[first.token_start : first.token_end]
                if first.token_start == last.token_start
                else line[first.start : last.end]
            )
            findings.append(
                Finding(
                    file=file,
                    line=line_number,
                    column=first.start + 1,
                    message=f"Forbidden term '{raw_forbidden}' found in '{context}'.",
                    suggestion=f"Use canonical term '{entry.term}' ({entry.definition}).",
                )
            )
    return findings


def _extract_active_line(line: str) -> tuple[str, set[tuple[str, ...]] | None]:
    ignore_match = IGNORE_PATTERN.search(line)
    if ignore_match is None:
        return line, set()
    raw_bracket = ignore_match.group(1)
    if raw_bracket is None:
        return "", None
    ignored = {norm for part in raw_bracket.split(",") if (norm := normalize_subwords(part))}
    return line[: ignore_match.start()], ignored


def _finding_sort_key(finding: Finding) -> tuple[str, int, int, str]:
    return (finding.file.as_posix(), finding.line, finding.column, finding.message)


def _extract_line_subwords(line: str) -> list[_SubwordSpan]:
    return [
        _SubwordSpan(
            word=singularize(sub.group(0).lower()),
            start=tok.start() + sub.start(),
            end=tok.start() + sub.end(),
            token_start=tok.start(),
            token_end=tok.end(),
        )
        for tok in TOKEN_PATTERN.finditer(line)
        for sub in SUBWORD_PATTERN.finditer(tok.group(0))
    ]


def _matches_window(
    line: str, window: list[_SubwordSpan], forbidden_words: tuple[str, ...]
) -> bool:
    if any(span.word != expected for span, expected in zip(window, forbidden_words, strict=True)):
        return False
    return all(
        line[prev_span.end : next_span.start].strip("_- \t") == ""
        for prev_span, next_span in zip(window, window[1:], strict=False)
    )


def _build_ignore_matcher(
    base_dir: Path, exclude: tuple[str, ...], source_path: Path
) -> pathspec.PathSpec:
    resolved_source = source_path.resolve()
    patterns: list[str] = [
        ".git/",
        f"/{resolved_source.relative_to(base_dir).as_posix()}",
    ]
    gitignore_path = base_dir / ".gitignore"
    if gitignore_path.is_file():
        patterns.extend(gitignore_path.read_text(encoding="utf-8").splitlines())
    patterns.extend(exclude)
    return pathspec.PathSpec.from_lines("gitignore", patterns)


def _resolve_search_roots(
    base_dir: Path, configured_paths: tuple[Path, ...], targets: Sequence[Path] | None
) -> tuple[list[Path], list[Finding]]:
    if targets is None:
        roots = [
            resolved
            for rel_path in configured_paths
            if (resolved := (base_dir / rel_path).resolve()).exists()
        ]
        return roots, []

    roots: list[Path] = []
    findings: list[Finding] = []
    for target in targets:
        resolved = _resolve_target(base_dir, target)
        if resolved.exists():
            roots.append(resolved)
        else:
            findings.append(
                Finding(
                    file=target,
                    message=f"Target path '{target}' does not exist.",
                    suggestion="Provide an existing target_file or directory path.",
                )
            )
    return roots, findings


def _discover_target_files(
    base_dir: Path, roots: Sequence[Path], ignore_matcher: pathspec.PathSpec
) -> list[Path]:
    discovered: list[Path] = []
    for target in roots:
        if target.is_file():
            discovered.append(target)
            continue

        for root_str, dirnames, filenames in os.walk(target):
            root_path = Path(root_str)
            dirnames[:] = sorted(
                dirname
                for dirname in dirnames
                if not _is_ignored(root_path / dirname, base_dir, ignore_matcher, is_dir=True)
            )
            for filename in sorted(filenames):
                file_path = root_path / filename
                if not _is_ignored(file_path, base_dir, ignore_matcher, is_dir=False):
                    discovered.append(file_path)

    return list(dict.fromkeys(discovered))


def _is_ignored(
    path: Path, base_dir: Path, ignore_matcher: pathspec.PathSpec, *, is_dir: bool
) -> bool:
    if not path.is_relative_to(base_dir):
        return False
    rel_posix = path.relative_to(base_dir).as_posix()
    return ignore_matcher.match_file(rel_posix) or (
        is_dir and ignore_matcher.match_file(f"{rel_posix}/")
    )


def _resolve_target(base_dir: Path, target: Path) -> Path:
    if target.exists():
        return target.resolve()
    joined = base_dir / target
    return joined.resolve() if joined.exists() else target.resolve()


def _read_text_file(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
        return None if b"\x00" in raw else raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
