import { z } from 'zod';
import { sseData } from './sse';

const sourceSchema = z.object({ id: z.string(), text: z.string() });

/** The wire contract with the Python service (see python-service/app/main.py). */
const eventSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('step'), node: z.string(), sources: z.array(sourceSchema).optional() }),
  z.object({ type: z.literal('token'), text: z.string() }),
  z.object({ type: z.literal('done') }),
  z.object({ type: z.literal('error'), message: z.string() }),
]);
const askSchema = z.object({ answer: z.string(), sources: z.array(sourceSchema) });

export type LangGraphEvent = z.infer<typeof eventSchema>;
export type AskResult = z.infer<typeof askSchema>;

export interface LangGraphClient {
  /** Streams events as the graph runs. Aborting `signal` cancels the upstream HTTP request. */
  stream(question: string, signal?: AbortSignal): AsyncGenerator<LangGraphEvent>;
  /** Runs the graph to completion and returns the final answer (used by tools). */
  ask(question: string, signal?: AbortSignal): Promise<AskResult>;
}

export function createLangGraphClient(options: {
  baseUrl: string;
  fetch?: typeof globalThis.fetch;
}): LangGraphClient {
  const doFetch = options.fetch ?? globalThis.fetch;
  const base = options.baseUrl.replace(/\/$/, '');
  const post = (path: string, question: string, signal?: AbortSignal) =>
    doFetch(`${base}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question }),
      signal,
    });

  return {
    async *stream(question, signal) {
      const res = await post('/v1/stream', question, signal);
      if (!res.ok || !res.body) {
        throw new Error(`LangGraph service returned HTTP ${res.status} for /v1/stream`);
      }
      for await (const data of sseData(res.body)) {
        yield eventSchema.parse(JSON.parse(data));
      }
    },
    async ask(question, signal) {
      const res = await post('/v1/ask', question, signal);
      if (!res.ok) throw new Error(`LangGraph service returned HTTP ${res.status} for /v1/ask`);
      return askSchema.parse(await res.json());
    },
  };
}
