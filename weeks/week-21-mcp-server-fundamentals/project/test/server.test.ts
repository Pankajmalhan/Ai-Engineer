import { Client } from '@modelcontextprotocol/client';
import { InMemoryTransport } from '@modelcontextprotocol/client';
import { describe, expect, it } from 'vitest';
import { AssistantError, type AssistantClient } from '../src/assistantClient.js';
import { ASK_CODEBASE_DESCRIPTION, MAX_QUESTION_CHARS, createServer, formatAnswer } from '../src/server.js';

/** Wire a real Client to a real McpServer in-process: exercises schema validation + the protocol, no sockets. */
async function connect(assistant: AssistantClient) {
    const client = new Client({ name: 'test-harness', version: '1.0.0' });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await Promise.all([client.connect(clientTransport), createServer(assistant).connect(serverTransport)]);
    return client;
}

const textOf = (result: { content: unknown }) => (result.content as { type: string; text: string }[]).map(c => c.text).join('\n');

describe('ask_codebase tool', () => {
    it('is advertised with a description and a JSON Schema requiring `question`', async () => {
        const client = await connect({ ask: async () => ({ answer: '', sources: [] }) });
        const { tools } = await client.listTools();
        expect(tools).toHaveLength(1);
        expect(tools[0]).toMatchObject({ name: 'ask_codebase', description: ASK_CODEBASE_DESCRIPTION });
        expect(tools[0]!.inputSchema).toMatchObject({
            type: 'object',
            required: ['question'],
            properties: { question: { type: 'string' } }
        });
    });

    it('forwards the question to the assistant and returns answer + sources as text', async () => {
        const asked: string[] = [];
        const client = await connect({
            ask: async q => {
                asked.push(q);
                return { answer: 'Routing lives in router.ts.', sources: ['src/router.ts', 'src/app.ts'] };
            }
        });
        const result = await client.callTool({ name: 'ask_codebase', arguments: { question: '  where is routing?  ' } });
        expect(asked).toEqual(['where is routing?']); // trimmed by the schema before the handler runs
        expect(result.isError).toBeFalsy();
        expect(textOf(result)).toBe('Routing lives in router.ts.\n\nSources:\n- src/router.ts\n- src/app.ts');
    });

    it.each([
        ['missing', {}],
        ['wrong type', { question: 42 }],
        ['blank', { question: '   ' }],
        ['too long', { question: 'x'.repeat(MAX_QUESTION_CHARS + 1) }]
    ])('rejects a %s question before the assistant is called', async (_name, args) => {
        let calls = 0;
        const client = await connect({
            ask: async () => {
                calls++;
                return { answer: '', sources: [] };
            }
        });
        const result = await client.callTool({ name: 'ask_codebase', arguments: args }).catch(e => e);
        // Depending on the era, invalid input surfaces as isError or a thrown protocol error; never as a handler call.
        expect(result.isError === true || result instanceof Error).toBe(true);
        expect(calls).toBe(0);
    });

    it('turns an assistant failure into an isError result the model can read', async () => {
        const client = await connect({
            ask: async () => {
                throw new AssistantError('cannot reach assistant at http://localhost:8000: fetch failed', 'unreachable');
            }
        });
        const result = await client.callTool({ name: 'ask_codebase', arguments: { question: 'hi' } });
        expect(result.isError).toBe(true);
        expect(textOf(result)).toBe('ask_codebase failed (unreachable): cannot reach assistant at http://localhost:8000: fetch failed');
    });

    it('passes the request abort signal down so a cancelled call cancels the upstream request', async () => {
        let upstream: AbortSignal | undefined;
        const client = await connect({
            ask: (_q, signal) => {
                upstream = signal;
                return new Promise(() => {}); // never resolves
            }
        });
        const ac = new AbortController();
        const call = client.callTool({ name: 'ask_codebase', arguments: { question: 'slow' } }, { signal: ac.signal });
        await new Promise(r => setTimeout(r, 20));
        expect(upstream).toBeDefined();
        expect(upstream!.aborted).toBe(false);
        ac.abort();
        await call.catch(() => {});
        await new Promise(r => setTimeout(r, 20));
        expect(upstream!.aborted).toBe(true);
    });
});

describe('formatAnswer', () => {
    it('omits the Sources block when there are none', () => {
        expect(formatAnswer('just this', [])).toBe('just this');
    });
});
