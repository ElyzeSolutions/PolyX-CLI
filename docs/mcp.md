# X MCP and PolyX

X provides hosted Model Context Protocol endpoints:

- `https://api.x.com/mcp` for X API tools
- `https://docs.x.com/mcp` for X developer documentation

These are complementary to PolyX. PolyX remains the deterministic ingestion
layer for applications that need typed responses, cache keys, spend controls,
output formats, and explicit routing domains.

## Recommended use

- Use an app-only bearer token for read-only, automated PolyX ingestion.
- Use X MCP for bounded agent exploration such as read-only search, news,
  trends, and lookups.
- Use OAuth 2.0 through X's `xurl mcp` bridge when an agent genuinely needs user
  context or write access.
- Use the Docs MCP server for developer assistance; it does not need X account
  credentials.

Applications should allowlist MCP tools and keep their calls behind the same
budget, audit, and domain boundaries as other providers. Do not give an
automated trading agent posting, deletion, bookmark, or account-management
tools merely because the server exposes them.

Browser cookies are a separate local fallback for PolyX's unofficial GraphQL
client. They should not be uploaded to a hosted application or used as a
substitute for OAuth. A future interactive sign-in should prefer scoped OAuth
through the X MCP bridge.
