import { describe, expect, it } from 'vitest';
import { createLangGraphClient } from '../src/langgraphClient';
import { bodyFrom, collect, sse } from './helpers';

function clientWith(respond: (url: string, init: RequestInit) => Response) {
  const calls: { url: string; init: RequestInit }[] = [];
  const fetchFn = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return respond(String(url), init ?? {});
  }) as typeof fetch;
  return { client: createLangGraphClient({ baseUrl: 'http://py:8000/', fetch: fetchFn }), calls };
}

describe('LangGraph client', () => {
  it('POSTs the question and yields validated events in order', async () => {
    const { body } = bodyFrom([
      sse({ type: 'step', node: 'retrieve', sources: [{ id: 'a', text: 't' }] }),
      sse({ type: 'token', text: 'Hi' }),
      sse({ type: 'done' }),
    ]);
    const { client, calls } = clientWith(() => new Response(body, { status: 200 }));
    const events = await collect(client.stream('why?'));

    expect(events.map((e) => e.type)).toEqual(['step', 'token', 'done']);
    expect(calls[0]!.url).toBe('http://py:8000/v1/stream'); // trailing slash in baseUrl is normalised
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ question: 'why?' });
  });

  it('passes the abort signal to fetch', async () => {
    const { body } = bodyFrom([sse({ type: 'done' })]);
    const { client, calls } = clientWith(() => new Response(body));
    const controller = new AbortController();
    await collect(client.stream('q', controller.signal));
    expect(calls[0]!.init.signal).toBe(controller.signal);
  });

  it('throws on a non-200 response', async () => {
    const { client } = clientWith(() => new Response('nope', { status: 502 }));
    await expect(collect(client.stream('q'))).rejects.toThrow(/HTTP 502/);
  });

  it('rejects an event that violates the contract instead of passing garbage downstream', async () => {
    const { body } = bodyFrom([sse({ type: 'token' })]); // missing "text"
    const { client } = clientWith(() => new Response(body));
    await expect(collect(client.stream('q'))).rejects.toThrow();
  });

  it('ask() returns the parsed answer and sources', async () => {
    const { client, calls } = clientWith(() => Response.json({ answer: 'A', sources: [{ id: 'x', text: 'y' }] }));
    expect(await client.ask('q')).toEqual({ answer: 'A', sources: [{ id: 'x', text: 'y' }] });
    expect(calls[0]!.url).toBe('http://py:8000/v1/ask');
  });
});
