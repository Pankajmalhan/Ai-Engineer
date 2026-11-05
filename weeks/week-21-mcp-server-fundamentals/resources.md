# Week 21 -- Resources

## From the roadmap

**Primary:** MCP TypeScript SDK documentation (modelcontextprotocol.io/docs/sdk) -- *no URL given in the plan; use the refreshed link below.*

**Secondary:** MCP Inspector README (github.com/modelcontextprotocol/inspector) -- *no URL given in the plan; use the refreshed link below.*

**Refreshed links (the roadmap flags this week as `fix`: the spec was rewritten 2026-07-28):**

* [MCP TypeScript SDK (current, v2)](https://ts.sdk.modelcontextprotocol.io/) -- `@modelcontextprotocol/server` / `client`
* [MCP Inspector docs (2026-07-28 spec)](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector)

## Added by Claude while building this week (all read during the build)

* [Key Changes -- MCP 2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog) -- statelessness, `server/discover`, deprecations (also listed under Week 22 in the roadmap)
* [Upgrading from v1.x to v2 -- SDK migration guide](https://ts.sdk.modelcontextprotocol.io/v2/migration/upgrade-to-v2) -- the codemod and what changed (`registerTool`, `serveStdio`, `createMcpHandler`)
* [SDK "Build a server" / first-server guide](https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-server.html)
* [SDK: returning tool errors (`isError`)](https://ts.sdk.modelcontextprotocol.io/v2/servers/errors.html)
* [SDK troubleshooting: log to stderr over stdio](https://ts.sdk.modelcontextprotocol.io/v2/troubleshooting.html)
* [Inspector -- CLI client](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector/cli.md) (scriptable `--method tools/call`)

## Looking ahead (Week 22)

* [Streamable HTTP transport (2026-07-28)](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http.md)
* [Hono -- Getting Started](https://hono.dev/docs/getting-started/basic)
