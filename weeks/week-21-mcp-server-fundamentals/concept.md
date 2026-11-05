# Week 21 -- MCP server fundamentals

> **Why the plan text and this project differ.** The roadmap marks this week `fix`: the MCP spec was
> rewritten on **2026-07-28** (superseding 2025-11-25) and made the protocol largely stateless. The plan says
> to install `@modelcontextprotocol/sdk`; that is the **v1** single package. The current line is **v2**, split into
> `@modelcontextprotocol/server` and `@modelcontextprotocol/client`, and implements the 2026-07-28 spec. The project
> builds on v2 and its docs. Most tutorials you will find online (`server.tool(...)`, `new StdioServerTransport()`,
> "the `initialize` handshake") describe the older shape.

## Overview

You have an assistant (Python, LangGraph, behind a FastAPI endpoint) that can answer questions about a codebase.
The problem is distribution: every editor and chat app would need its own bespoke integration. **MCP (Model Context
Protocol)** is the standard socket for this. An *MCP server* describes what it can do (tools, data, prompt
templates); any *MCP client* (Claude Desktop, Claude Code, Cursor, the Inspector) can discover and use it without
custom glue. This week you write the smallest useful server -- one tool, `ask_codebase`, a thin adapter over your
FastAPI endpoint -- and prove it works with the Inspector before any real client touches it. Weeks 22-24 grow it
(resources, HTTP transport, npm publish).

## Core concept, in depth

### 1. Who talks to whom

```
 HOST app (Claude Desktop, Cursor, ...)        <- owns the LLM and the user
   └─ MCP CLIENT (one per server)              <- speaks the protocol, 1:1 with a server
         │  JSON-RPC 2.0 messages
         ▼
      MCP SERVER (your code)                   <- exposes capabilities; calls your real backend
         └─ FastAPI assistant, DB, filesystem...
```

The host decides *whether* to call your tool (the model picks it based on the text you wrote); the client does the
mechanics; your server never talks to the model. Mentally, MCP is "LSP for AI tools": N hosts x M servers without
N x M integrations.

### 2. The three server primitives -- and who controls each

| Primitive | What it is | Who decides to use it | Example |
|---|---|---|---|
| **Tool** | a function with typed input the model can call; may have side effects | the **model** | `ask_codebase(question)` |
| **Resource** | read-only data addressed by URI that the app can load into context | the **application / user** | `index://stats` (Week 22) |
| **Prompt** | a reusable, parameterised message template | the **user** (e.g. a slash command) | "review this diff" |

This week is tools only. The control distinction is the design heuristic: if the *model* should be able to decide
to do it mid-conversation, it is a tool; if the *app* should attach it as context, it is a resource.

### 3. What actually goes over the wire

A tool is described to clients by `tools/list`:

```json
{ "name": "ask_codebase",
  "description": "Ask a natural-language question about the indexed codebase ...",
  "inputSchema": { "type": "object", "properties": { "question": { "type": "string", "minLength": 1 } },
                   "required": ["question"] } }
```

and invoked by `tools/call` with `{ "name": "ask_codebase", "arguments": { "question": "..." } }`, which returns
`{ "content": [{ "type": "text", "text": "..." }], "isError": false }`. Everything else is detail around these two
messages. Three consequences worth internalising:

* **The `description` and the schema are your prompt.** The model never sees your code; it sees these strings.
  "Ask a question" is a bad description; "Ask about architecture / where something is implemented; prefer over
  grepping for conceptual questions" tells the model *when* to reach for it. Field `.describe()` text flows into the
  JSON Schema too.
* **Validation is the SDK's job, not yours.** In v2 you pass a zod object as `inputSchema`; the SDK derives the JSON
  Schema, validates every call against it, and only then runs your handler (verified in `test/server.test.ts`:
  blank / wrong-type / over-long input never reaches the assistant).
* **There are two error channels.** A *protocol* error (bad JSON-RPC, unknown tool) is a failed request. A *tool*
  error is a successful request whose result has `isError: true` and a message. Use the second for anything the model
  could act on ("assistant unreachable, try later") -- it reads that text and can recover or explain; a protocol
  error is opaque to it.

### 4. Transports: how bytes move

* **stdio** -- the client spawns your server as a child process and exchanges newline-delimited JSON-RPC on
  stdin/stdout. Single client, local, zero networking. This week.
  **Rule: stdout is the wire. Never `console.log`.** One stray line corrupts the stream (the e2e test proves the
  failure by switching the startup log to stdout). Log to stderr; hosts show it in the server log.
* **Streamable HTTP** -- a single HTTP endpoint, many clients, remote. Week 22. (The older HTTP+SSE transport is now
  formally *Deprecated*.)

### 5. What the 2026-07-28 revision changed (and why the SDK looks different)

Before: a client opened a connection, ran an `initialize` handshake to negotiate version and capabilities, and (over
HTTP) carried an `Mcp-Session-Id`. The server was a long-lived, stateful object -- awkward to scale horizontally or
run serverless. After (from the spec changelog):

* **No `initialize`/`initialized` handshake and no protocol-level sessions.** Every request carries its protocol
  version and client capabilities in `_meta` (`io.modelcontextprotocol/protocolVersion`, `.../clientCapabilities`);
  servers identify themselves in each result's `_meta`. A version mismatch returns an `UnsupportedProtocolVersion`
  error. Anything that needs cross-call state uses explicit, server-minted handles passed as ordinary tool arguments.
* **`server/discover`**: servers must answer it with their supported versions, capabilities and identity (clients may
  call it first, or use it as a compatibility probe).
* **Results carry `resultType`** (`"complete"` or `"input_required"`); the server-initiated requests of the old
  protocol (roots, sampling, elicitation) become a "multi round-trip" pattern where the server returns what it needs
  and the client retries.
* **Deprecated**: Roots, Sampling and Logging (use tool params / direct provider APIs / stderr + OpenTelemetry),
  HTTP+SSE. `tools/list` should be returned in a deterministic order (helps client caching and LLM prompt-cache hits);
  list results carry `ttlMs` / `cacheScope` hints.

What this means for your code: build the server in a **factory** (`createServer()` returns a fresh `McpServer`), and
serve it with `serveStdio(() => createServer())` (stdio) or `createMcpHandler(() => createServer())` (HTTP, Week 22).
The SDK can now construct a server per request, so a server must not stash per-connection state in module scope.
`serveStdio` serves both eras: the e2e test connects once with the default (legacy handshake) and once pinned to
`2026-07-28` (`client.getProtocolEra() === 'modern'`) against the same process.

### 6. Worked example: this week's `ask_codebase`

```ts
server.registerTool(
  'ask_codebase',
  { description: '...when to use it...',
    inputSchema: z.object({ question: z.string().trim().min(1).max(2000) }) },
  async ({ question }, ctx) => {
    try {
      const { answer, sources } = await assistant.ask(question, ctx.mcpReq.signal); // abort propagates
      return { content: [{ type: 'text', text: formatAnswer(answer, sources) }] };
    } catch (err) {
      if (err instanceof AssistantError)
        return { content: [{ type: 'text', text: `ask_codebase failed (${err.kind}): ${err.message}` }], isError: true };
      throw err;
    }
  });
```

Design choices to notice: the adapter (`assistantClient.ts`) is injectable so the tool is tested without a network;
failures are classified (`unreachable` / `timeout` / `http` / `bad-response`) so the model gets a *useful* error;
the request's abort signal is forwarded, so if the user cancels in the host, the HTTP request to your assistant is
cancelled too (a test fails when you remove the forwarding).

### 7. MCP Inspector: test the server alone

The Inspector is "Postman for MCP": it spawns your server (or connects to a URL), shows `tools/list`, lets you fill the
schema form, run the call, and shows the raw JSON-RPC both ways. It ships as three clients over one core: web
(`npx @modelcontextprotocol/inspector <cmd>`), `--cli` (scriptable, good for CI), and `--tui`. Always get it working
here first: if Claude Desktop shows nothing, you will not know whether the server, the config, or the host is at fault.
It needs Node >= 22.19. It does **not** forward your shell environment to the server it spawns (use `-e KEY=VAL` or the
UI's env box) -- a real gotcha hit while building this week.

## Why it matters in production

* **One integration, every host.** The same package works in Claude Desktop, Claude Code and Cursor; your IDE-assistant
  story (Q2's goal) is "one config line", not three plugins.
* **The tool contract is an API you ship to models.** Renaming a tool or changing its schema silently changes agent
  behaviour for everyone who installed it. Treat names, descriptions and schemas as versioned interface.
* **Failure modes are different from a web API.** The caller is a model: vague errors cause retry loops or invented
  answers; slow tools stall a conversation (hence timeouts + cancellation); oversized results burn the context window
  (a reason to cap/shape what `ask_codebase` returns rather than dumping files).
* **Security.** A server runs with your user's privileges and its output goes straight into a model's context: treat
  tool *outputs* as untrusted input (prompt injection via retrieved text -- Week 7's lesson), keep tools least-privilege,
  validate all arguments, and keep secrets in `env`, not in the repo.

## Tradeoffs & comparisons

| Choice | When it wins | Cost |
|---|---|---|
| **MCP server** vs. a bespoke IDE extension | many hosts, you want one maintained surface | a protocol layer + the hosts' UX limits |
| **MCP tool** vs. the Week 15 Vercel-AI-SDK tool | MCP: tool is consumed by *someone else's* model/host. AI SDK: you own the agent loop and model | AI SDK tools aren't discoverable by other apps; MCP tools don't give you control over the loop |
| **stdio** vs. **Streamable HTTP** | stdio: local, single user, simplest, no auth. HTTP: shared/remote/multi-client, needs auth + deployment (Week 22) | stdio = one process per client; HTTP = you run and secure a service |
| **Thin adapter** (this week) vs. **in-process logic** | adapter: Python stays the source of truth, one codebase for logic | extra hop + latency; need the backend running |
| **Tool** vs. **resource** | model-initiated action/query -> tool; app-attached read-only context -> resource | choosing wrong makes the primitive unusable in some hosts |
| SDK **v2** vs **v1** | v2 for new work (current spec, stateless, `registerTool`, `serveStdio`) | v1 tutorials/snippets don't transfer 1:1; v1->v2 has a codemod |

## Common pitfalls

1. **Writing to stdout** (`console.log`, a library's debug print) in a stdio server -- corrupts JSON-RPC; symptom is a
   host-side "invalid JSON"/disconnect.
2. **Relative paths and missing env in the host config.** Claude Desktop doesn't start in your project directory and passes
   only the `env` you list. Use absolute paths; set `ASSISTANT_URL` in `env`. (Same applies to the Inspector.)
3. **A vague `description`** -- the model won't call the tool, or calls it for the wrong things.
4. **Throwing for expected failures** instead of returning `isError` with an actionable message.
5. **No timeout / no cancellation** on the upstream call -- a hung backend hangs the conversation.
6. **Module-level state** in the server (a cache keyed to "the connection") -- breaks under the stateless model;
   mutable state should live in your backend or behind explicit handles.
7. **Following pre-2026-07-28 tutorials**: `server.tool(...)`, `StdioServerTransport` by hand, relying on `initialize`
   or `Mcp-Session-Id`.
8. **Forgetting to restart the host** after editing its config (Claude Desktop reads it only at launch).

## Check yourself

1. In the host / client / server picture, who decides to call `ask_codebase`, and what information do they use to decide?
2. Name the three server primitives and say which of them the *model* controls. Why is `ask_codebase` a tool and not a resource?
3. A tool fails because the backend is down. When should the handler return `isError: true` instead of throwing, and what should the message contain?
4. Why must a stdio server never `console.log`, and where should logs go?
5. What did the 2026-07-28 spec remove, what replaced it, and how does that change how you structure `createServer` / how you serve it?
6. Your Inspector run says "unreachable" even though you `export`ed `ASSISTANT_URL`. What is happening and how do you fix it (Inspector and Claude Desktop)?
