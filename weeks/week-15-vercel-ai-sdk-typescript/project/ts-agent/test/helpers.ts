import type { LangGraphClient, LangGraphEvent } from '../src/langgraphClient';

export const enc = new TextEncoder();

/** A ReadableStream<Uint8Array> that yields the given pieces, and records whether it was cancelled. */
export function bodyFrom(pieces: (string | Uint8Array)[]) {
  const state = { cancelled: false };
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= pieces.length) return controller.close();
      const piece = pieces[i++]!;
      controller.enqueue(typeof piece === 'string' ? enc.encode(piece) : piece);
    },
    cancel() {
      state.cancelled = true;
    },
  });
  return { body, state };
}

export async function collect<T>(iter: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const item of iter) out.push(item);
  return out;
}

export const sse = (obj: unknown) => `data: ${JSON.stringify(obj)}\n\n`;

/** Parse an SSE Response body into JSON chunks. */
export async function readChunks(res: Response): Promise<{ type: string; [k: string]: any }[]> {
  const { sseData } = await import('../src/sse');
  const chunks = [];
  for await (const data of sseData(res.body!)) if (data !== '[DONE]') chunks.push(JSON.parse(data));
  return chunks;
}

export function fakeLangGraph(overrides: Partial<LangGraphClient> = {}): LangGraphClient & {
  askCalls: string[];
  signals: (AbortSignal | undefined)[];
} {
  const askCalls: string[] = [];
  const signals: (AbortSignal | undefined)[] = [];
  return {
    askCalls,
    signals,
    async *stream(_q, signal) {
      signals.push(signal);
      const events: LangGraphEvent[] = [
        { type: 'step', node: 'retrieve', sources: [{ id: 'doc-1', text: 'first doc' }] },
        { type: 'token', text: 'Hello ' },
        { type: 'token', text: 'world' },
        { type: 'step', node: 'generate' },
        { type: 'done' },
      ];
      yield* events;
    },
    async ask(question) {
      askCalls.push(question);
      return { answer: `answer to: ${question}`, sources: [{ id: 'doc-1', text: 'first doc' }] };
    },
    ...overrides,
  };
}
