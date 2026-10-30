# glossary-checker-cli

A CLI checker that validates a project's `glossary.toml` and inspects configured target files for forbidden terms, emitting findings with actionable suggestions.

## Installation

Requires Python 3.12+.

Install as a standalone CLI tool or add as a development dependency with [`uv`](https://docs.astral.sh/uv/):

```bash
uv tool install git+https://github.com/philipp-vocal-logic/glossary-checker-cli
# or in a project:
uv add --dev git+https://github.com/philipp-vocal-logic/glossary-checker-cli
```

## Configuration

Define canonical terms, definitions, and forbidden terms in `glossary.toml`:

```toml
[settings]
paths = ["."]
exclude = ["uv.lock"]
similarity_threshold = 0.65

[[terms]]
term = "customer"
definition = "An entity that purchases goods from the platform."
forbidden_terms = ["client", "buyer_profile"]
```

### Settings

- `paths` (default: `["."]`) — Target files or directories to check relative to the `glossary.toml` directory.
- `exclude` (default: `[]`) — Additional gitignore-style patterns to skip. `.git/`, the active `glossary.toml`, `.gitignore` patterns, and binary files are excluded automatically.
- `similarity_threshold` (default: `0.65`) — Minimum Jaccard similarity (`0.0` to `1.0`) between normalized non-stopword definitions before reporting overlapping terms.

### What Gets Checked

1. **Glossary validation**: Reports empty terms or definitions, duplicate canonical terms, collisions between canonical terms and `forbidden_terms`, overlapping definitions (`>= similarity_threshold`), and definitions that use a `forbidden_term`.
2. **Target file checking**: Splits identifiers and prose into normalized lowercase singular subwords across `snake_case`, `camelCase`, `PascalCase`, `kebab-case`, and acronyms. For example, forbidding `"client"` or `"buyer_profile"` matches `fetch_client`, `HTTPClients`, `buyerProfile`, and `"buyer profiles"`.

## Usage

Run the checker against the workspace:

```bash
uv run glossary
uv run glossary src/
uv run glossary --config path/to/glossary.toml
```

Example finding output:

```text
src/billing.py:12:5: Forbidden term 'client' found in 'fetch_client'. Suggestion: Use canonical term 'customer' (An entity that purchases goods from the platform.).
```

### Inline Suppression

Suppress all findings on a line with `glossary: ignore`, or specific comma-separated terms with `glossary: ignore[term1, term2]`. Supported trailing comment styles are `#`, `//`, `--`, `/* ... */`, and `<!-- ... -->`:

```python
http_session = httpx.Client()  # glossary: ignore[client]
```

### Exit Codes

- `0`: No findings.
- `1`: One or more findings reported.
- `2`: Configuration file could not be read or parsed.

## Development

See [`glossary.toml`](glossary.toml) for this repository's canonical terms and definitions.

Enable the repository's Git hooks (`.githooks/pre-commit` and `.githooks/commit-msg`):

```bash
git config core.hooksPath .githooks
```

Run checks manually:

```bash
uv lock --check
uv run ruff check .
uv run ruff format --check .
uv run glossary
uv run symbol
uv run architecture
uv run pytest
```
