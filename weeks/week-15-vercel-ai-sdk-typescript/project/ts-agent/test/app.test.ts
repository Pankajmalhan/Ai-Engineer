import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app';
import type { LangGraphEvent } from '../src/langgraphClient';
import { sseData } from '../src/sse';
import { fakeLangGraph, readChunks } from './helpers';
import { scriptedModel, textModel, toolCallStream, textStream } from './mockModels';

const post = (app: ReturnType<typeof createApp>, path: string, body: unknown, init: RequestInit = {}) =>
  app.request(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), ...init });

const userMessage = (text: string) => ({ messages: [{ id: 'm1', role: 'user', parts: [{ type: 'text', text }] }] });
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('POST /api/langgraph/stream (pass-through)', () => {
  const app = () => createApp({ model: textModel('unused', 'x'), langgraph: fakeLangGraph() });

  it('re-frames LangGraph events as an AI SDK UI message stream', async () => {
    const res = await post(app(), '/api/langgraph/stream', { question: 'q' });
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    expect(res.headers.get('x-vercel-ai-ui-message-stream')).toBe('v1');

    const chunks = await readChunks(res);
    const types = chunks.map((c) => c.type);
    expect(types[0]).toBe('start');
    expect(types).toContain('finish');
    expect(types.indexOf('text-start')).toBeLessThan(types.indexOf('text-delta'));
    expect(types.lastIndexOf('text-delta')).toBeLessThan(types.indexOf('text-end'));

    const deltas = chunks.filter((c) => c.type === 'text-delta');
    expect(deltas.map((d) => d.delta).join('')).toBe('Hello world');
    expect(new Set(chunks.filter((c) => c.type.startsWith('text-')).map((c) => c.id)).size).toBe(1); // one text block
    const steps = chunks.filter((c) => c.type === 'data-step').map((c) => c.data.node);
    expect(steps).toEqual(['retrieve', 'generate']);
    expect(chunks.find((c) => c.type === 'data-step')!.data.sources[0].id).toBe('doc-1');
  });

  it('streams: the first token reaches the client BEFORE the upstream has finished', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    let upstreamFinished = false;
    const lg = fakeLangGraph({
      async *stream() {
        yield { type: 'token', text: 'first ' } satisfies LangGraphEvent;
        await gate; // upstream is stuck here until the test says go
        yield { type: 'token', text: 'second' } satisfies LangGraphEvent;
        yield { type: 'done' } satisfies LangGraphEvent;
        upstreamFinished = true;
      },
    });
    const res = await post(createApp({ model: textModel('u', 'x'), langgraph: lg }), '/api/langgraph/stream', { question: 'q' });

    const received: string[] = [];
    for await (const data of sseData(res.body!)) {
      if (data === '[DONE]') continue;
      const chunk = JSON.parse(data);
      if (chunk.type !== 'text-delta') continue;
      received.push(chunk.delta);
      if (received.length === 1) {
        // we hold the first token while the upstream is still blocked => nothing is buffered until the end
        expect(upstreamFinished).toBe(false);
        release();
      }
    }
    expect(received.join('')).toBe('first second');
  }, 5000);

  it('turns an error event from the service into an error chunk (not a dropped connection)', async () => {
    const lg = fakeLangGraph({
      async *stream() {
        yield { type: 'token', text: 'partial' } satisfies LangGraphEvent;
        yield { type: 'error', message: 'RuntimeError: model down' } satisfies LangGraphEvent;
      },
    });
    const chunks = await readChunks(await post(createApp({ model: textModel('u', 'x'), langgraph: lg }), '/api/langgraph/stream', { question: 'q' }));
    const error = chunks.find((c) => c.type === 'error');
    expect(error?.errorText).toBe('LangGraph service error: RuntimeError: model down');
    expect(chunks.some((c) => c.type === 'text-delta')).toBe(true); // what was already sent stays sent
  });

  it('reports an unreachable service the same way', async () => {
    const lg = fakeLangGraph({
      // eslint-disable-next-line require-yield
      async *stream() {
        throw new Error('connect ECONNREFUSED 127.0.0.1:8000');
      },
    });
    const chunks = await readChunks(await post(createApp({ model: textModel('u', 'x'), langgraph: lg }), '/api/langgraph/stream', { question: 'q' }));
    expect(chunks.find((c) => c.type === 'error')?.errorText).toContain('ECONNREFUSED');
  });

  it('cancels the upstream request when the client disconnects', async () => {
    let upstreamSignal: AbortSignal | undefined;
    const lg = fakeLangGraph({
      async *stream(_q, signal) {
        upstreamSignal = signal;
        yield { type: 'token', text: 'a' } satisfies LangGraphEvent;
        await new Promise((_, reject) => signal?.addEventListener('abort', () => reject(new Error('aborted'))));
      },
    });
    const controller = new AbortController();
    const res = await post(createApp({ model: textModel('u', 'x'), langgraph: lg }), '/api/langgraph/stream', { question: 'q' }, { signal: controller.signal });
    for await (const data of sseData(res.body!)) {
      if (data !== '[DONE]' && JSON.parse(data).type === 'text-delta') {
        controller.abort();
        break;
      }
    }
    await wait(20);
    expect(upstreamSignal?.aborted).toBe(true);
  });

  it.each([{}, { question: '' }, { question: '   ' }, { question: 5 }])('rejects an invalid body %j with 400', async (body) => {
    const res = await post(app(), '/api/langgraph/stream', body);
    expect(res.status).toBe(400);
  });
});

describe('POST /api/agent (tool calling)', () => {
  it('runs the tool loop: model -> tool call -> execute -> model -> final text', async () => {
    const lg = fakeLangGraph();
    const model = scriptedModel([
      () => toolCallStream('searchKnowledgeBase', { query: 'what is LiteLLM?' }),
      () => textStream('LiteLLM is ', 'a proxy.') as never,
    ]);
    const res = await post(createApp({ model, langgraph: lg }), '/api/agent', userMessage('what is LiteLLM?'));
    const chunks = await readChunks(res);
    const types = chunks.map((c) => c.type);

    expect(lg.askCalls).toEqual(['what is LiteLLM?']); // the SDK executed OUR tool with the model's input
    const call = chunks.find((c) => c.type === 'tool-input-available')!;
    expect(call).toMatchObject({ toolName: 'searchKnowledgeBase', input: { query: 'what is LiteLLM?' } });
    const output = chunks.find((c) => c.type === 'tool-output-available')!;
    expect(output.output).toEqual({ answer: 'answer to: what is LiteLLM?', sourceIds: ['doc-1'] });
    expect(types.indexOf('tool-output-available')).toBeLessThan(types.indexOf('text-delta')); // answer comes after the result

    expect(chunks.filter((c) => c.type === 'text-delta').map((c) => c.delta).join('')).toBe('LiteLLM is a proxy.');
    expect(model.doStreamCalls).toHaveLength(2); // one call to decide, one to answer
    const secondPrompt = model.doStreamCalls[1]!.prompt;
    expect(secondPrompt[secondPrompt.length - 1]!.role).toBe('tool'); // the tool result was fed back to the model
    expect(model.doStreamCalls[0]!.tools?.map((t) => t.name).sort()).toEqual(['getBrowserContext', 'getCurrentTime', 'searchKnowledgeBase', 'setTheme']);
  });

  it('bounds the loop: a model that keeps calling tools stops at maxSteps', async () => {
    const model = scriptedModel([() => toolCallStream('getCurrentTime', { timeZone: 'UTC' })]);
    const res = await post(createApp({ model, langgraph: fakeLangGraph(), maxSteps: 3 }), '/api/agent', userMessage('loop forever'));
    await readChunks(res);
    expect(model.doStreamCalls).toHaveLength(3);
  });

  it('a throwing tool becomes a tool error the model sees, and the run continues', async () => {
    const model = scriptedModel([
      () => toolCallStream('getCurrentTime', { timeZone: 'Mars/Olympus' }),
      () => textStream('Sorry, that time zone is unknown.') as never,
    ]);
    const chunks = await readChunks(await post(createApp({ model, langgraph: fakeLangGraph() }), '/api/agent', userMessage('time on Mars?')));
    expect(chunks.some((c) => c.type === 'tool-output-error')).toBe(true);
    expect(chunks.filter((c) => c.type === 'text-delta').map((c) => c.delta).join('')).toContain('unknown');
    expect(model.doStreamCalls).toHaveLength(2);
  });

  it('streams model text token by token (several deltas, not one block)', async () => {
    const model = textModel('gpt-4o-mini', 'a', 'b', 'c', 'd');
    const chunks = await readChunks(await post(createApp({ model, langgraph: fakeLangGraph() }), '/api/agent', userMessage('hi')));
    expect(chunks.filter((c) => c.type === 'text-delta')).toHaveLength(4);
  });

  it.each([{}, { messages: [] }, { messages: [{ role: 'user' }] }])('rejects an invalid body %j with 400', async (body) => {
    const res = await post(createApp({ model: textModel('u', 'x'), langgraph: fakeLangGraph() }), '/api/agent', body);
    expect(res.status).toBe(400);
  });
});

describe('POST /api/agent (browser-side tools)', () => {
  const browserContext = { url: 'http://localhost:5173/', title: 'Agent chat', language: 'en-US', viewport: { width: 1200, height: 800 }, selection: 'hello' };
  const assistantWithToolOutput = {
    id: 'a1',
    role: 'assistant',
    parts: [{ type: 'tool-getBrowserContext', toolCallId: 'call-1', state: 'output-available', input: {}, output: browserContext }],
  };

  it('a tool without execute ends the response at the tool call -- the server does not invent a result', async () => {
    const model = scriptedModel([() => toolCallStream('getBrowserContext', {})]);
    const chunks = await readChunks(await post(createApp({ model, langgraph: fakeLangGraph() }), '/api/agent', userMessage('what page am I on?')));
    const types = chunks.map((c) => c.type);

    expect(chunks.find((c) => c.type === 'tool-input-available')).toMatchObject({ toolName: 'getBrowserContext' });
    expect(types).not.toContain('tool-output-available'); // nobody on the server can answer it
    expect(types).not.toContain('text-delta');
    expect(model.doStreamCalls).toHaveLength(1); // the loop paused here, waiting for the browser
    expect(model.doStreamCalls[0]!.tools?.map((t) => t.name)).toEqual(
      expect.arrayContaining(['getBrowserContext', 'setTheme', 'searchKnowledgeBase', 'getCurrentTime']),
    );
  });

  it('second request: the browser sends the tool output back and the server continues the loop', async () => {
    const model = scriptedModel([() => textStream('You are on "Agent chat".') as never]);
    const app = createApp({ model, langgraph: fakeLangGraph() });
    const res = await post(app, '/api/agent', {
      messages: [{ id: 'u1', role: 'user', parts: [{ type: 'text', text: 'what page am I on?' }] }, assistantWithToolOutput],
    });
    const chunks = await readChunks(res);

    expect(chunks.filter((c) => c.type === 'text-delta').map((c) => c.delta).join('')).toBe('You are on "Agent chat".');
    // the model saw the browser's output as a tool result
    const prompt = model.doStreamCalls[0]!.prompt;
    const toolMessage = prompt.find((m) => m.role === 'tool')!;
    expect(JSON.stringify(toolMessage)).toContain('Agent chat');
    expect(JSON.stringify(toolMessage)).toContain('getBrowserContext');
  });

  it('a browser-side tool error is passed to the model so it can explain instead of crashing', async () => {
    const model = scriptedModel([() => textStream('I could not read the page.') as never]);
    const res = await post(createApp({ model, langgraph: fakeLangGraph() }), '/api/agent', {
      messages: [
        { id: 'u1', role: 'user', parts: [{ type: 'text', text: 'dark mode please' }] },
        { id: 'a1', role: 'assistant', parts: [{ type: 'tool-setTheme', toolCallId: 'c', state: 'output-error', input: { theme: 'dark' }, errorText: 'storage blocked' }] },
      ],
    });
    await readChunks(res);
    expect(JSON.stringify(model.doStreamCalls[0]!.prompt)).toContain('storage blocked');
  });
});
