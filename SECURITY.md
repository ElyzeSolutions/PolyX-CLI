# Security Policy

## Supported versions

Only the latest release on `main` is supported.

## Reporting a vulnerability

- Do not open public issues for vulnerabilities, exposed tokens, or private data.
- Use GitHub private vulnerability reporting if it is enabled for this repository.
- If private reporting is unavailable, contact the maintainers privately through the organization rather than posting details publicly.

## Secrets handling

- Never commit real credentials, cookies, or API tokens.
- Use `.env.example` for documented variables and keep local secrets in ignored `.env` files.
- Rotate any credential immediately if you suspect it was exposed.
