# glossary-checker-cli

A CLI checker that validates a project's `glossary.toml` and inspects configured target files for forbidden terms, emitting findings with actionable suggestions.

## Configuration

Define canonical terms, definitions, and forbidden terms in `glossary.toml`:

```toml
[settings]
paths = ["."]
exclude = [".git/", "glossary.toml", "uv.lock"]
similarity_threshold = 0.65

[[terms]]
term = "customer"
definition = "An entity that purchases goods from the platform."
forbidden_terms = ["client", "buyer_profile"]
```

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

Suppress findings on a specific line with `glossary: ignore` or `glossary: ignore[term]`:

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
uv run pytest
uv run ruff check .
uv run glossary
uv run symbol
uv run architecture
```
