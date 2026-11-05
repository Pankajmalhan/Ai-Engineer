import { tool } from 'ai';
import { z } from 'zod';
import type { LangGraphClient } from './langgraphClient';

/**
 * Tools the TypeScript agent can call. For each one the SDK needs only three things: a
 * description (what the model reads to decide when to call it), an `inputSchema` (zod -> JSON
 * schema for the model, and runtime validation of what the model sends back), and `execute`.
 * The SDK then runs the loop: model emits a tool call -> SDK validates input -> runs `execute`
 * -> feeds the result back to the model -> repeat until the model answers or `stopWhen` hits.
 */
export function createTools(deps: { langgraph: LangGraphClient; now?: () => Date }) {
  const now = deps.now ?? (() => new Date());
  return {
    searchKnowledgeBase: tool({
      description:
        'Search the internal knowledge base (answered by the Python LangGraph service). Use for any question about LangGraph, the Vercel AI SDK, LiteLLM or the supervisor pattern.',
      inputSchema: z.object({
        query: z.string().min(1).describe('A self-contained question to look up'),
      }),
      execute: async ({ query }, { abortSignal }) => {
        const { answer, sources } = await deps.langgraph.ask(query, abortSignal);
        return { answer, sourceIds: sources.map((s) => s.id) };
      },
    }),
    getCurrentTime: tool({
      description: 'Get the current date and time in an IANA time zone, e.g. "Asia/Kolkata".',
      inputSchema: z.object({
        timeZone: z.string().default('UTC').describe('IANA time zone name'),
      }),
      execute: async ({ timeZone }) => {
        // Throws RangeError for an unknown zone; the SDK turns that into a tool error the model can read and recover from.
        const formatted = new Intl.DateTimeFormat('en-US', {
          dateStyle: 'full',
          timeStyle: 'long',
          timeZone,
        }).format(now());
        return { timeZone, formatted };
      },
    }),
  };
}

export type AgentTools = ReturnType<typeof createTools>;

/**
 * Browser-side tools. Note what is MISSING: there is no `execute`. The server only tells the model
 * these tools exist (description + input schema). When the model calls one, `streamText` has
 * nothing to run, so the step ends with an unanswered tool call and the HTTP response finishes.
 * The web page runs the tool (it has the DOM, the selection, the theme), then re-sends the
 * conversation with the tool's output attached, and the server continues from there. The agent
 * loop therefore spans several requests instead of one -- see web/src/clientTools.ts.
 */
export const clientTools = {
  getBrowserContext: tool({
    description:
      "Read the user's current browser tab: page URL, title, language, viewport size and any text they have selected. Use when the question is about what the user is looking at.",
    inputSchema: z.object({}),
  }),
  setTheme: tool({
    description: "Switch the web page's colour theme. Use when the user asks for dark or light mode.",
    inputSchema: z.object({ theme: z.enum(['light', 'dark']) }),
  }),
};

export const CLIENT_TOOL_NAMES = Object.keys(clientTools);
