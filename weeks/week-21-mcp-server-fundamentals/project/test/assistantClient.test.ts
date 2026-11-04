import { describe, expect, it } from 'vitest';
import { AssistantError, createAssistantClient } from '../src/assistantClient.js';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

describe('assistant client', () => {
    it('POSTs {question} to /v1/ask and returns the validated body', async () => {
        let seen: { url: string; body: unknown } | undefined;
        const client = createAssistantClient({
            baseUrl: 'http://assistant:8000',
            fetch: async (url, init) => {
                seen = { url: String(url), body: JSON.parse(String(init?.body)) };
                return json({ answer: 'in router.ts', sources: ['src/router.ts'] });
            }
        });
        await expect(client.ask('where is routing?')).resolves.toEqual({ answer: 'in router.ts', sources: ['src/router.ts'] });
        expect(seen).toEqual({ url: 'http://assistant:8000/v1/ask', body: { question: 'where is routing?' } });
    });

    it('defaults missing sources to []', async () => {
        const client = createAssistantClient({ baseUrl: 'http://a', fetch: async () => json({ answer: 'x' }) });
        await expect(client.ask('q')).resolves.toEqual({ answer: 'x', sources: [] });
    });

    it('classifies a non-2xx as kind=http and keeps the status and body', async () => {
        const client = createAssistantClient({ baseUrl: 'http://a', fetch: async () => new Response('nope', { status: 503 }) });
        await expect(client.ask('q')).rejects.toMatchObject({ kind: 'http', message: expect.stringContaining('503: nope') });
    });

    it('classifies a malformed body as kind=bad-response', async () => {
        const client = createAssistantClient({ baseUrl: 'http://a', fetch: async () => json({ nope: true }) });
        await expect(client.ask('q')).rejects.toMatchObject({ kind: 'bad-response' });
    });

    it('classifies a connection failure as kind=unreachable', async () => {
        const client = createAssistantClient({
            baseUrl: 'http://a',
            fetch: async () => {
                throw new TypeError('fetch failed');
            }
        });
        await expect(client.ask('q')).rejects.toMatchObject({ kind: 'unreachable' });
    });

    it('times out as kind=timeout when the assistant hangs', async () => {
        const client = createAssistantClient({
            baseUrl: 'http://a',
            timeoutMs: 20,
            fetch: (_url, init) =>
                new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))
        });
        const err = await client.ask('q').catch(e => e);
        expect(err).toBeInstanceOf(AssistantError);
        expect(err.kind).toBe('timeout');
    });

    it('propagates a caller abort as an abort, not as "unreachable"', async () => {
        const ac = new AbortController();
        const client = createAssistantClient({
            baseUrl: 'http://a',
            fetch: (_url, init) =>
                new Promise((_resolve, reject) => init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))
        });
        const pending = client.ask('q', ac.signal);
        ac.abort();
        const err = await pending.catch(e => e);
        expect(err).not.toBeInstanceOf(AssistantError);
        expect(err.name).toBe('AbortError');
    });
});
