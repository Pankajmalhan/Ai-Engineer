import { describe, expect, it } from 'vitest';
import { consumeUIMessageStream } from '../src/client';
import { sse } from './helpers';

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** A Response whose body is produced slowly, like a real model. */
function slowResponse(events: unknown[], delayMs: number): Response {
  const encoder = new TextEncoder();
  let i = 0;
  return new Response(
    new ReadableStream({
      async pull(controller) {
        if (i >= events.length) return controller.close();
        if (i > 0) await wait(delayMs);
        controller.enqueue(encoder.encode(sse(events[i++])));
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' } },
  );
}

describe('consumeUIMessageStream', () => {
  it('hands text to the caller as it arrives, and measures first-text vs total time', async () => {
    const events = [
      { type: 'start' },
      { type: 'text-start', id: 't' },
      { type: 'text-delta', id: 't', delta: 'Hel' },
      { type: 'text-delta', id: 't', delta: 'lo' },
      { type: 'text-delta', id: 't', delta: '!' },
      { type: 'text-end', id: 't' },
      { type: 'finish' },
    ];
    const seen: { delta: string; at: number }[] = [];
    const t0 = performance.now();
    const stats = await consumeUIMessageStream(slowResponse(events, 30), {
      onText: (delta) => seen.push({ delta, at: performance.now() - t0 }),
    }, t0);

    expect(stats.text).toBe('Hello!');
    expect(stats.textDeltas).toBe(3);
    expect(seen.map((s) => s.delta)).toEqual(['Hel', 'lo', '!']);
    // each delta was delivered ~30ms apart rather than all at the end
    expect(seen[1]!.at - seen[0]!.at).toBeGreaterThanOrEqual(20);
    expect(stats.firstTextMs!).toBeLessThan(stats.totalMs - 40);
  });

  it('reports tool calls, tool results, steps and errors through onInfo', async () => {
    const info: string[] = [];
    const stats = await consumeUIMessageStream(
      slowResponse(
        [
          { type: 'data-step', data: { node: 'retrieve', sources: [{ id: 'doc-1' }] } },
          { type: 'tool-input-available', toolCallId: 'c', toolName: 'searchKnowledgeBase', input: { query: 'q' } },
          { type: 'tool-output-available', toolCallId: 'c', output: { answer: 'A' } },
          { type: 'error', errorText: 'boom' },
        ],
        0,
      ),
      { onInfo: (l) => info.push(l) },
    );
    expect(info).toEqual([
      'step: retrieve -> sources [doc-1]',
      'tool call: searchKnowledgeBase({"query":"q"})',
      'tool result: {"answer":"A"}',
      'error: boom',
    ]);
    expect(stats.toolCalls).toEqual(['searchKnowledgeBase']);
    expect(stats.errors).toEqual(['boom']);
    expect(stats.firstTextMs).toBeUndefined();
  });

  it('throws with the status and body on a non-2xx response', async () => {
    await expect(consumeUIMessageStream(new Response('bad request', { status: 400 }))).rejects.toThrow(/HTTP 400: bad request/);
  });
});
