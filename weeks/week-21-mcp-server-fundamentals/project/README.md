# Week 21 project -- a minimal TypeScript MCP server (`ask_codebase`)

A stdio MCP server with one tool, `ask_codebase(question)`, that forwards the question to the Python
assistant's `POST /v1/ask` (the FastAPI service from Weeks 13-15) and returns the answer plus the
source files it was grounded in.

```
Claude Desktop / Claude Code / Cursor / MCP Inspector      <- MCP client (spawns the server)
        |  JSON-RPC over stdin/stdout
        v
src/index.ts  --serveStdio-->  src/server.ts (McpServer + ask_codebase)
                                      |  src/assistantClient.ts : fetch + timeout + zod-validated reply
                                      v
                               FastAPI assistant  POST /v1/ask  ->  {"answer": "...", "sources": [...]}
```

| File | What it does |
|---|---|
| `src/server.ts` | `createServer(assistant)` -- a *factory* returning a fresh `McpServer` with the tool registered (zod input schema, `isError` on failure, request abort signal forwarded) |
| `src/assistantClient.ts` | `POST /v1/ask` with timeout; classifies failures (`unreachable` / `timeout` / `http` / `bad-response`); validates the body |
| `src/index.ts` | entry point: `serveStdio(() => createServer(...))`. Logs to **stderr** only |
| `src/fakeAssistant.ts` | tiny stand-in for the FastAPI service (same contract) so you can run everything with no Python / keys |
| `claude_desktop_config.example.json` | the config block for Claude Desktop |

SDK note: the plan names `@modelcontextprotocol/sdk` -- that is the **v1** single package. This project uses
**v2** (`@modelcontextprotocol/server` + `@modelcontextprotocol/client` for tests), which implements the
2026-07-28 spec. See `../concept.md`.

## Install and test

Needs Node >= 22.19 (the Inspector's requirement).

```bash
npm install
npm run typecheck
npm test        # 20 tests: client (7), tool over in-memory transport (9), real stdio child process (4)
```

No network, API keys, or Python needed: the end-to-end test spawns `src/index.ts` as a child process and points it at
the fake assistant.

## Run it against a backend

```bash
# Option A -- the real Week 15 LangGraph service (offline demo model unless OPENAI_API_KEY is set)
cd ../../week-15-vercel-ai-sdk-typescript/project/python-service && uv run uvicorn app.main:create_app --factory --port 8000

# Option B -- the fake backend (no Python)
npm run fake-assistant          # listens on :8000
```

## Test with the MCP Inspector (before any client)

```bash
npm run inspect                  # web UI: click Connect -> Tools -> ask_codebase -> Run Tool
# (the launcher prints a URL with a per-launch token; set ASSISTANT_URL in the UI's Environment Variables
#  if your backend is not on :8000)

# headless, same client core:
npx @modelcontextprotocol/inspector --cli -e ASSISTANT_URL=http://localhost:8000 \
  npx tsx src/index.ts --method tools/list
npx @modelcontextprotocol/inspector --cli -e ASSISTANT_URL=http://localhost:8000 \
  npx tsx src/index.ts --method tools/call --tool-name ask_codebase --tool-arg question="how does auth work?"
```

Gotcha seen while building this: the Inspector does **not** pass your shell's environment to the server it
spawns, so `export ASSISTANT_URL=...` is silently ignored and the tool reports `unreachable`. Use `-e KEY=VALUE`
(CLI) or the Environment Variables box (UI). Claude Desktop behaves the same way -- put it in the config's `env`.

## Connect Claude Desktop

1. Copy `claude_desktop_config.example.json`'s `mcpServers` entry into
   `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), replacing both `/ABSOLUTE/PATH/...`.
   Use absolute paths: Claude Desktop does not start the server in your project directory.
2. Fully quit and reopen Claude Desktop.
3. Start the backend (above), then ask something like *"Use ask_codebase to explain how auth works."*
   Server logs are in `~/Library/Logs/Claude/mcp-server-codebase-assistant.log`.

Claude Code: `claude mcp add codebase-assistant -e ASSISTANT_URL=http://localhost:8000 -- /ABSOLUTE/PATH/.../node_modules/.bin/tsx /ABSOLUTE/PATH/.../src/index.ts`

> Not verified from this scaffold: the Claude Desktop step itself (it is a GUI app). Everything it relies on
> -- the stdio framing, the tool list, a real call through the Inspector CLI -- was exercised.

## What the tests cover

* **client**: request shape, default `sources`, each failure kind, timeout, and that a *caller abort* is not
  mislabelled as "unreachable".
* **tool (in-memory Client <-> McpServer)**: the advertised JSON Schema; input is trimmed; missing / wrong-type /
  blank / over-long questions never reach the assistant; an assistant failure becomes an `isError` result the
  model can read; cancelling the MCP call aborts the upstream HTTP request.
* **stdio e2e (child process)**: tool list + call over real stdin/stdout, a client pinned to the **2026-07-28**
  revision (`getProtocolEra() === 'modern'`), backend 500 -> `isError` and the server survives, unreachable backend
  -> `isError`, and that logs go to stderr (verified by temporarily switching to `console.log` and watching the test fail).
