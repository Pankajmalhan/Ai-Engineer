# Week 15 -- Vercel AI SDK and the TypeScript agent layer

## Overview

Your agent logic lives in Python (LangGraph), but the places people actually use it -- an IDE
extension, a web app, a CLI -- are usually TypeScript. The **TypeScript agent layer** is the thin
service in between: it speaks the model providers' APIs, defines tools, and, most importantly,
**streams** -- so the user sees text as it is generated, not after the whole answer is done. The
**Vercel AI SDK** (package `ai`) is the library most TypeScript teams reach for to build that
layer: one API across providers, streaming as the default, typed tools, and a wire format that
front-end hooks already understand. This week you put it in front of the Week 13-14 LangGraph
world: a Hono server with two routes, a LiteLLM-backed fallback, and a terminal client that proves
tokens arrive incrementally.

```
 browser page (web/, useChat)  /  terminal client  /  IDE extension
        |  POST, reads Server-Sent Events (AI SDK "UI message stream")
        v
 TypeScript agent layer  (Hono + `ai`)                      <-- this week's TS code
   /api/langgraph/stream : re-frame LangGraph's stream, no LLM here
   /api/agent            : streamText + tools  --(tool: searchKnowledgeBase)-->  Python LangGraph service
        |  model calls: OpenAI, optional fallback model via LiteLLM                 (FastAPI + SSE)
        v
 providers
```

## Core concept, in depth

### 1. Why the AI SDK is the default TypeScript choice (and where that claim has limits)

What it gives you that raw provider SDKs don't:

* **One interface over many providers.** A model is just a value (`openai('gpt-4o-mini')`,
  `createOpenAICompatible({...}).chatModel('gpt-4o')`). `streamText`, `generateText` and the
  tool loop don't care which one you pass, so swapping or falling back is a one-line change.
* **Streaming is the primary path**, not an add-on: `streamText` returns immediately and you
  consume parts as they arrive.
* **Typed tools:** a zod `inputSchema` gives the model a JSON schema *and* validates what the
  model sends back *and* types your `execute` function's argument.
* **A wire protocol the UI already speaks.** The "UI message stream" (SSE of JSON chunks) is what
  `useChat`-style hooks consume, so a custom backend -- even a LangGraph one -- is a drop-in.
* **Middleware and test doubles** (`wrapLanguageModel`, `MockLanguageModelV4`): cross-cutting
  behaviour (our fallback) and deterministic tests without a network.

Honest limits. "TypeScript-native choice" is a judgement call, not a law: LangGraph.js/LangChain.js
and Mastra are real alternatives, and if the whole system is Python you don't need any of this.
The AI SDK also **moves fast**. Majors 5, 6 and 7 each changed streaming/tool APIs, so *read the
migration guide for the major you install and build against live docs*. Things that bit or
differ in v7 while building this week:

| Old tutorial / v5-6 habit | v7 reality (what this project uses) |
|---|---|
| `stepCountIs(5)` | `isStepCount(5)` (the old name still exported as an alias) |
| `result.toUIMessageStreamResponse()` | `createUIMessageStreamResponse({ stream: toUIMessageStream({ stream: result.stream }) })` |
| `system:` | `instructions:` (`system` still accepted) |
| `MockLanguageModelV2/V3`, `finishReason: 'stop'` | `MockLanguageModelV4`, `finishReason: { unified: 'stop', raw: undefined }` |
| `npm i ai @ai-sdk/openai` | a plain `npm install` gave me provider versions matching the **`ai-v6` dist-tag** (they implement model spec V3, not V4). Install `@ai-sdk/openai@latest` etc. so provider and `ai` majors match |

### 2. How streaming actually works, hop by hop

A streamed answer crosses up to four process boundaries, and **every one of them must forward
chunks as they arrive**. One buffering hop and the user sees nothing until the end -- the
symptom is "it works, but feels slow".

1. **LangGraph (Python).** `graph.astream(..., stream_mode=["updates", "messages"])` yields
   `updates` when a node finishes (retrieval done) and `messages` for each token a model emits
   *inside* a node (the `generate` node). Our node calls `await llm.ainvoke(...)`; LangGraph
   attaches a streaming callback so tokens surface while the call is still running.
2. **FastAPI.** A `StreamingResponse` over an async generator that `yield`s one
   `data: {json}\n\n` per event. `Cache-Control: no-cache` and `X-Accel-Buffering: no` stop
   proxies from holding the response.
3. **TypeScript layer.** `for await (const event of langgraph.stream(...))` and, for each token,
   `writer.write({ type: 'text-delta', ... })` immediately. Nothing is collected into an array.
4. **Client.** Reads the response body with a reader and prints each delta on arrival.

**Server-Sent Events (SSE)** is just a text format over a long-lived HTTP response: events
separated by a blank line, payload on `data:` lines. Two parsing traps, both tested in
`test/sse.test.ts`: a network chunk can end **mid-event** or even **mid-UTF-8-character**, so
you buffer until the blank line and decode with `{ stream: true }`.

**The UI message stream** adds structure on top of SSE. Text is a *block*:
`text-start {id}` -> many `text-delta {id, delta}` -> `text-end {id}`; the whole message is
bracketed by `start` ... `finish`; the stream ends with `[DONE]`. Other chunk types carry tool
calls (`tool-input-available`, `tool-output-available`, `tool-output-error`) and your own data
(`data-<name>`, which we use for the `data-step` "retrieve finished" progress event). Because the
format is typed, one stream can carry text, tool activity and progress together.
Gotcha found in testing: `streamText` emits the closing `finish` chunk for you, but a stream
you build by hand with `createUIMessageStream` does not -- write it yourself.

**Errors mid-stream.** By the time the model fails after emitting 50 tokens, the HTTP status
(200) was sent long ago. Errors must therefore travel **in-band** as an `error` chunk. The SDK
masks error text by default so provider internals don't leak to browsers; use `onError` to
choose what to reveal (we reveal our own LangGraph-service errors, and mask model errors).

**Cancellation.** If the user closes the terminal / navigates away, `request.signal` aborts.
We pass that signal to the `fetch` that talks to Python (and to `streamText`, and into tools),
so the Python generator is cancelled and you stop paying for tokens nobody reads. A test checks
the upstream signal really flips.

**Measure it.** *Time to first token* (TTFT) is the metric streaming improves. The terminal
client prints it next to total time: in the offline demo the first text appears at ~60-90 ms
while the whole answer takes ~1.1 s.

### 3. Tool calling: what "the SDK handles it" means

You write three things per tool; the SDK does the loop.

```ts
searchKnowledgeBase: tool({
  description: 'Search the internal knowledge base ...',          // what the model reads to decide
  inputSchema: z.object({ query: z.string().min(1) }),            // JSON schema for the model + validation
  execute: async ({ query }, { abortSignal }) => langgraph.ask(query, abortSignal),
})
```

`streamText({ model, tools, stopWhen: isStepCount(5) })` then repeats: **step 1** the model
streams a tool call -> SDK validates the input against the schema -> runs `execute` -> appends the
result to the conversation -> **step 2** calls the model again with the result -> ... until the
model answers in plain text or `stopWhen` trips. Without a `stopWhen` the loop stops after one
step, so the tool result is never summarised; with a bad model that keeps calling tools,
`isStepCount` is your circuit breaker (tested: a model that never stops is cut at `maxSteps`).
If `execute` throws, the SDK reports a `tool-output-error` and gives the model the error text, so
it can recover ("that time zone doesn't exist") instead of the request dying.

**Design question this raises:** you now have *two* places an agent can live. Pass-through
(`/api/langgraph/stream`) hands the whole conversation to LangGraph; the TS agent
(`/api/agent`) keeps the conversation and treats LangGraph as **one tool**. That is Week 14's
"sub-agents as tools" pattern with a language boundary in the middle. Use pass-through when the
Python graph owns the behaviour; use the TS agent when the front-end needs its own tools
(editor actions, UI state) alongside the Python knowledge.

### 4. Providers: OpenAI primary, optional LiteLLM fallback

* **Primary:** `@ai-sdk/openai`, model from `OPENAI_MODEL` (default `gpt-4o-mini`). The plan's original
  primary was Claude Sonnet; it was swapped for OpenAI because no Anthropic key was available. Because
  every provider is just a model value, going back is one function in `models.ts`. Note that
  `openai('...')` calls OpenAI's **Responses API** by default; `openai.chat('...')` selects the older
  Chat Completions API if you ever need it.
* **Fallback:** **LiteLLM** is a proxy that exposes *one OpenAI-compatible endpoint* in front of
  many providers. Because the AI SDK has a generic OpenAI-compatible provider, "GPT-4o via
  LiteLLM" is `createOpenAICompatible({ baseURL: 'http://localhost:4000/v1' }).chatModel('gpt-4o')`
  -- no OpenAI-specific code, and swapping the backing model later happens in LiteLLM config.
* **The fallback itself** is a `wrapLanguageModel` middleware: if `doStream()` throws before
  streaming starts, replay the *same call options* on the fallback model.

Decisions baked into `withFallback` (each has a test):

| Situation | Behaviour | Why |
|---|---|---|
| Primary fails before first token (HTTP 503, network) | use fallback | the user has seen nothing yet; restart is invisible |
| Primary fails **mid-stream** | surface the error, **no** fallback | restarting would show a second, different answer after partial text |
| Client aborted | re-throw, **no** fallback | nobody is waiting; don't spend a call |
| Both fail | fallback's error propagates | the most recent failure is the actionable one |

Also know: this wrapper fires on the *first* error, before the SDK's `maxRetries` loop retries
the primary. Latency-first; if you'd rather retry the primary twice first, move fallback to the
retry layer. Fallback can also be done *outside* the SDK -- in LiteLLM's own router config, or
via the AI Gateway's `models` provider option -- which keeps the logic in one place for every
client, at the cost of a hop you must operate.

### 5. Where the agent loop runs: server, browser, or both

A common first instinct is "do the agent in the front end instead of Python". Half of that is
right. The **loop** (call the model, run tools, feed results back, repeat) can be *driven* from
the page, and some tools can *only* run there. What must not happen is the **model call**
originating in browser code with a real API key: anyone can open dev tools and take it. So the
work is split by who has what:

| Piece | Runs in | Why |
|---|---|---|
| API keys, `streamText`, provider fallback | TS agent layer (server) | secrets never reach the page |
| `searchKnowledgeBase`, `getCurrentTime` (have `execute`) | TS agent layer (server) | need network access to the Python service |
| `useChat` conversation state, rendering the stream, auto-resubmit | **browser** (`web/src/App.tsx`) | it is the UI |
| `getBrowserContext`, `setTheme` (no `execute` on the server) | **browser** (`web/src/clientTools.ts`) | only the page can see its URL, selection and theme, or change its look |

**A browser-side tool call, step by step.** The loop spans several HTTP requests:

1. The page POSTs the conversation to `/api/agent`.
2. The model streams a call to `getBrowserContext`. The server declared that tool with *no*
   `execute`, so there is nothing to run: the response ends with `finishReason: "tool-calls"` and
   an unanswered tool call. (A server test asserts the server does not invent a result and does not
   call the model a second time.)
3. In the page, `onToolCall` fires; we run the tool locally and call `addToolOutput(...)`. Do
   **not** `await` it inside `onToolCall` -- the docs warn it can deadlock the chat.
4. `sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls` notices every tool call in
   the last assistant message now has an output and POSTs the conversation again. Without that
   option the chat just stalls after the tool runs.
5. The assistant message now carries a `tool-getBrowserContext` part in state `output-available`.
   The server converts it back into a model-level tool result, the model sees it, and streams the
   answer.

The server is **stateless** between those requests: the only memory is the `messages` array the
browser re-sends. That has a security consequence -- a client can send anything, including a forged
tool result -- so treat browser-supplied tool output as *user input*, never as authority. (Don't let
a "tool result" from the page unlock something the user couldn't do directly.)

**Writing a safe browser tool.** The tool's input is text a model produced, so validate it before
touching the page (`setTheme` parses with zod and rejects `{theme: "blue"}`). Its output is sent to
the model provider, so return a deliberately small subset: `getBrowserContext` returns URL, title,
language, viewport and the first 500 characters of the selection -- not cookies, storage or the DOM.
For sensitive actions the SDK also supports tool *approval* (ask the user before running).

**Variant not built here: an IDE extension.** An extension host is Node on the user's own machine,
so it can run `streamText` in-process with the user's own key and call editor APIs as tools -- no
server at all. The same tool definitions and loop apply; only the transport differs.

## Why it matters in production

* **Perceived latency.** An agent turn is often 5-30 s (retrieval + tool calls + generation).
  Streaming turns "blank for 20 s" into "text starts in under a second". Progress parts
  (`data-step`) make the silent phases visible too.
* **Where TypeScript runs.** Serverless/edge functions have request-duration limits and bill by
  time; a stream that stays open and forwards bytes is cheap, a buffered one hits timeouts.
* **Provider outages happen.** Provider 429s/5xx and rate limits are routine; a fallback converts an
  incident into a latency blip. It also changes your answer quality for those requests -- log which
  model served each response.
* **Cost leaks via abandoned requests.** Without abort propagation, closed tabs keep generating.
* **Contract drift across languages.** The TS layer and the Python service agree only by a wire
  format. We validate every upstream event with zod: a Python-side change fails loudly in one place
  rather than corrupting the stream silently.
* **Versioning.** A major upgrade of `ai` can break streaming or tools. Pin versions, keep the
  mock-model tests (they caught real API-shape changes this week), read the migration guide.

## Tradeoffs & comparisons

| Choice | Pros | Cons |
|---|---|---|
| **AI SDK (this week)** | unified providers, streaming default, typed tools, UI-ready protocol | fast-moving API; TS only; adds a service in front of Python |
| LangGraph.js / LangChain.js | same graph model as Python; one mental model | heavier; UI protocol not as standard; two graph runtimes to keep in sync |
| Raw provider SDKs | no abstraction, full control | you re-implement streaming parsing, tool loop, fallback per provider |
| Python-only (FastAPI -> client) | one language, no extra hop | front-end teams must parse your custom stream; no AI SDK UI hooks |
| Pass-through route | Python owns the logic; TS stays trivially thin | TS can't add tools or model fallback of its own |
| TS agent + LangGraph as a tool | TS-side tools, fallback, multi-provider | two LLM layers to reason about; extra latency per tool call |
| SSE | simple, works over plain HTTP, proxies/CDNs understand it | one-directional (client -> server uses normal requests) |
| WebSocket | bidirectional (cancel, barge-in, realtime audio) | stateful connections, more infra |

## Common pitfalls

1. **Buffering somewhere in the chain** -- collecting events before writing, a proxy that gzips or
   buffers (`X-Accel-Buffering: no`), or a framework that waits for the handler to finish.
2. **Provider/`ai` major mismatch** -- `npm` can resolve provider packages from the wrong dist-tag;
   they must implement the same model-spec version (V4 here).
3. **Following a v5/v6 tutorial on v7** (`stepCountIs`, `toUIMessageStreamResponse`, V2/V3 mocks).
4. **No `stopWhen`** -- the tool result is never fed back and the user gets a tool call, no answer.
5. **Hand-built streams missing `finish`** (or `text-start`/`text-end` pairs with inconsistent ids).
6. **Ignoring abort** -- upstream keeps generating after the client left.
7. **Falling back mid-stream** -- duplicated/contradictory answers.
8. **Assuming an SSE chunk is one event** -- it isn't; buffer to the blank line.
9. **Unvalidated cross-service events** -- a renamed field in Python becomes `undefined` in the UI.
10. **Leaking provider errors to clients**, or swallowing them silently -- choose with `onError`.
11. **Testing only against live models** -- slow, flaky, costs money. Mock the model, but also keep
    one real end-to-end check.
12. **Putting a provider key in browser code** -- it is public the moment the page loads. Keep the model call in the server layer; let the page call *your* route.
13. **Browser tools with no `sendAutomaticallyWhen`** -- the tool runs, the output is stored, and nothing is ever sent back: the chat appears to hang.
14. **`await`-ing `addToolOutput` inside `onToolCall`** -- can deadlock. Call it and return.
15. **Trusting the page's tool output on the server** -- it is client-controlled input.
16. **Over-sharing in tool results** -- everything a browser tool returns goes to the model provider.

## Check yourself

1. List the hops between the model's first token and the character appearing in the terminal.
   Which of them could silently turn a streaming system into a buffered one, and how did this
   project's test prove that ours doesn't?
2. HTTP 200 and headers are already sent when the model fails after 50 tokens. How does the
   client learn about the failure, and why is the error text masked by default?
3. `streamText` is given a tool but no `stopWhen`. Walk through what happens, then what changes
   with `stopWhen: isStepCount(5)`. What happens if `execute` throws?
4. Why does `withFallback` refuse to fall back after the primary has started streaming? What is
   the user-visible failure if it did?
5. LiteLLM is "OpenAI-compatible". Why does that mean no OpenAI-specific code is needed to use
   GPT-4o as the fallback, and what would you change to route the fallback to a different model?
6. When would you choose the pass-through route over the tool-calling agent route, and what do you
   give up?
7. Why can't the browser call the model directly with its own `streamText`, and what does the page do
   instead? Which pieces of the agent loop *can* live in the page?
8. Walk through the requests that happen when the model calls `getBrowserContext`. How many HTTP
   requests are there, what does the server's first response end with, and what happens if
   `sendAutomaticallyWhen` is missing?
9. A request arrives at `/api/agent` containing a `tool-setTheme` part in `output-available` state.
   Should the server trust it? What if the tool were `deleteProject` instead?
