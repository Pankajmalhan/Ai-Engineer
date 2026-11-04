import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { startFakeAssistant } from '../src/fakeAssistant.js';

/**
 * The real thing: spawn `src/index.ts` as a child process (exactly what Claude Desktop / the Inspector do),
 * talk JSON-RPC over its stdin/stdout, and let it call a real HTTP backend. Catches what in-memory tests can't:
 * stray stdout writes, a bad entry point, the stdio framing.
 */
let fake: Awaited<ReturnType<typeof startFakeAssistant>>;
beforeAll(async () => {
    fake = await startFakeAssistant();
});
afterAll(() => new Promise<void>(r => fake.server.close(() => r())));

async function spawnClient(assistantUrl: string, versionNegotiation?: ConstructorParameters<typeof Client>[1]) {
    const client = new Client({ name: 'e2e', version: '1.0.0' }, versionNegotiation);
    const stderr: string[] = [];
    const transport = new StdioClientTransport({
        command: process.execPath,
        args: ['--import', 'tsx', 'src/index.ts'],
        env: { ...process.env, ASSISTANT_URL: assistantUrl, ASSISTANT_TIMEOUT_MS: '2000' } as Record<string, string>,
        stderr: 'pipe'
    });
    transport.stderr?.on('data', d => stderr.push(String(d)));
    await client.connect(transport);
    return { client, stderr, close: () => client.close() };
}

const textOf = (result: { content: unknown }) => (result.content as { text: string }[]).map(c => c.text).join('\n');

describe('stdio server, end to end', () => {
    it('lists the tool and answers through the HTTP backend (legacy handshake)', async () => {
        const { client, stderr, close } = await spawnClient(fake.url);
        try {
            const { tools } = await client.listTools();
            expect(tools.map(t => t.name)).toEqual(['ask_codebase']);

            const result = await client.callTool({ name: 'ask_codebase', arguments: { question: 'how does auth work?' } });
            expect(result.isError).toBeFalsy();
            expect(textOf(result)).toContain('Fake answer to: how does auth work?');
            expect(textOf(result)).toContain('- src/auth/session.ts');
            expect(fake.questions).toContain('how does auth work?');
            expect(stderr.join('')).toContain('codebase-assistant MCP server on stdio'); // logs go to stderr, not the wire
        } finally {
            await close();
        }
    });

    it('also serves a client pinned to the 2026-07-28 (stateless) revision', async () => {
        const { client, close } = await spawnClient(fake.url, { versionNegotiation: { mode: { pin: '2026-07-28' } } });
        try {
            expect(client.getProtocolEra()).toBe('modern');
            const result = await client.callTool({ name: 'ask_codebase', arguments: { question: 'modern era?' } });
            expect(textOf(result)).toContain('Fake answer to: modern era?');
        } finally {
            await close();
        }
    });

    it('reports a backend 500 as a tool error, and the server keeps working afterwards', async () => {
        const { client, close } = await spawnClient(fake.url);
        try {
            const bad = await client.callTool({ name: 'ask_codebase', arguments: { question: 'boom' } });
            expect(bad.isError).toBe(true);
            expect(textOf(bad)).toContain('HTTP 500: upstream exploded');

            const good = await client.callTool({ name: 'ask_codebase', arguments: { question: 'fine' } });
            expect(good.isError).toBeFalsy();
        } finally {
            await close();
        }
    });

    it('reports an unreachable backend as a tool error instead of crashing', async () => {
        const { client, close } = await spawnClient('http://127.0.0.1:1');
        try {
            const result = await client.callTool({ name: 'ask_codebase', arguments: { question: 'anyone?' } });
            expect(result.isError).toBe(true);
            expect(textOf(result)).toContain('(unreachable)');
        } finally {
            await close();
        }
    });
});
