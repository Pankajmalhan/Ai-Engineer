import type { LanguageModelV4 } from '@ai-sdk/provider';
import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  isStepCount,
  streamText,
  toUIMessageStream,
  type UIMessage,
} from 'ai';
import { Hono } from 'hono';
import { z } from 'zod';
import type { LangGraphClient } from './langgraphClient';
import { clientTools, createTools } from './tools';

/** Custom data part streamed alongside the text so a UI/terminal can show pipeline progress. */
export type PipelineUIMessage = UIMessage<
  never,
  { step: { node: string; sources?: { id: string; text: string }[] } }
>;

const AGENT_INSTRUCTIONS =
  'You are a concise engineering assistant. For questions about LangGraph, the Vercel AI SDK, LiteLLM or the supervisor pattern, call searchKnowledgeBase and answer from its result. Use getCurrentTime for time questions. For questions about what the user is looking at in their browser (page, selection, screen) call getBrowserContext, and call setTheme when they ask for dark or light mode; those two run in the user\'s browser.';

const questionBody = z.object({ question: z.string().trim().min(1) });
const agentBody = z.object({
  messages: z.array(z.looseObject({ id: z.string(), role: z.enum(['user', 'assistant', 'system']), parts: z.array(z.unknown()) })).min(1),
});

export type AppDeps = {
  model: LanguageModelV4;
  langgraph: LangGraphClient;
  maxSteps?: number;
};

export function createApp({ model, langgraph, maxSteps = 5 }: AppDeps) {
  const app = new Hono();
  // Server tools run here (have `execute`); client tools are declared only and run in the browser.
  const tools = { ...createTools({ langgraph }), ...clientTools };

  app.get('/healthz', (c) => c.json({ ok: true }));

  /**
   * Route 1 -- pass-through. No LLM in TypeScript: the Python LangGraph service does the work and
   * we re-frame its SSE events as an AI SDK UI message stream, so any AI SDK client (useChat, the
   * terminal client) can consume a LangGraph backend unchanged.
   */
  app.post('/api/langgraph/stream', async (c) => {
    const parsed = questionBody.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) return c.json({ error: 'body must be {"question": "<non-empty string>"}' }, 400);
    const { question } = parsed.data;
    const signal = c.req.raw.signal; // aborts when the client disconnects -> cancels the upstream call

    const stream = createUIMessageStream<PipelineUIMessage>({
      execute: async ({ writer }) => {
        writer.write({ type: 'start' });
        const textId = 'langgraph-text';
        let textOpen = false;
        for await (const event of langgraph.stream(question, signal)) {
          if (event.type === 'step') {
            writer.write({ type: 'data-step', data: { node: event.node, sources: event.sources } });
          } else if (event.type === 'token') {
            if (!textOpen) {
              writer.write({ type: 'text-start', id: textId });
              textOpen = true;
            }
            writer.write({ type: 'text-delta', id: textId, delta: event.text });
          } else if (event.type === 'error') {
            throw new Error(event.message);
          }
        }
        if (textOpen) writer.write({ type: 'text-end', id: textId });
        // streamText's path emits this itself; a hand-built stream must close the message explicitly.
        writer.write({ type: 'finish', finishReason: 'stop' });
      },
      onError: (error) => `LangGraph service error: ${error instanceof Error ? error.message : String(error)}`,
    });
    return createUIMessageStreamResponse({ stream });
  });

  /**
   * Route 2 -- the TypeScript agent. The model (via the SDK) decides when to call tools; the SDK
   * validates tool input, runs `execute`, feeds results back and loops up to `maxSteps` steps.
   * One of the tools calls the same Python LangGraph service.
   */
  app.post('/api/agent', async (c) => {
    const parsed = agentBody.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) return c.json({ error: 'body must be {"messages": UIMessage[]}' }, 400);
    const messages = parsed.data.messages as unknown as UIMessage[];

    const result = streamText({
      model,
      instructions: AGENT_INSTRUCTIONS,
      messages: await convertToModelMessages(messages),
      tools,
      stopWhen: isStepCount(maxSteps),
      abortSignal: c.req.raw.signal,
    });
    return createUIMessageStreamResponse({
      stream: toUIMessageStream({
        stream: result.stream,
        // Error text is masked by default so provider details don't leak to clients; log instead.
        onError: (error) => {
          console.error('[agent] stream error:', error);
          return 'The model request failed. Check the server logs.';
        },
      }),
    });
  });

  return app;
}
