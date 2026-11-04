import { McpServer } from '@modelcontextprotocol/server';
import * as z from 'zod/v4';
import { AssistantError, type AssistantClient } from './assistantClient.js';

export const MAX_QUESTION_CHARS = 2000;

/** One tool, one job. The description is what the *model* reads to decide when to call it. */
export const ASK_CODEBASE_DESCRIPTION =
    'Ask a natural-language question about the indexed codebase (architecture, where something is implemented, ' +
    'conventions, how a flow works). Returns an answer plus the source files it was grounded in. ' +
    'Prefer this over grepping when the question is conceptual rather than an exact string.';

export function formatAnswer(answer: string, sources: string[]): string {
    if (sources.length === 0) return answer;
    return `${answer}\n\nSources:\n${sources.map(s => `- ${s}`).join('\n')}`;
}

/**
 * Build a fresh server. Factory, not singleton: under the 2026-07-28 spec a server can be
 * constructed per request, so it must not hold state that outlives a call.
 */
export function createServer(assistant: AssistantClient): McpServer {
    const server = new McpServer({ name: 'codebase-assistant', version: '0.1.0' });

    server.registerTool(
        'ask_codebase',
        {
            description: ASK_CODEBASE_DESCRIPTION,
            inputSchema: z.object({
                question: z.string().trim().min(1).max(MAX_QUESTION_CHARS).describe('The question, phrased as you would to a teammate')
            })
        },
        async ({ question }, ctx) => {
            try {
                const { answer, sources } = await assistant.ask(question, ctx.mcpReq.signal);
                return { content: [{ type: 'text', text: formatAnswer(answer, sources) }] };
            } catch (err) {
                // Tool-level failure: tell the model what went wrong so it can recover or explain,
                // instead of throwing (which becomes an opaque protocol error).
                if (err instanceof AssistantError) {
                    return { content: [{ type: 'text', text: `ask_codebase failed (${err.kind}): ${err.message}` }], isError: true };
                }
                throw err;
            }
        }
    );

    return server;
}
