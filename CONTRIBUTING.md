# Contributing

## Local setup

```bash
uv sync --extra ai --extra rich --extra dev
```

## Common commands

```bash
uv run pytest
uv run ruff check .
uv build
```

## Guidelines

- Keep the public CLI stable: the package installs as `polyx-cli`, but the command stays `polyx`.
- Prefer small, explicit changes over abstractions.
- Never commit real credentials. Use `.env.example` for documented variables and keep local secrets in ignored `.env` files.
