import { describe, expect, it } from 'vitest';
import { createTools } from '../src/tools';
import { fakeLangGraph } from './helpers';

const opts = (abortSignal?: AbortSignal) => ({ toolCallId: 't1', messages: [], abortSignal }) as never;

describe('tools', () => {
  it('searchKnowledgeBase calls the LangGraph service and returns answer + source ids', async () => {
    const lg = fakeLangGraph();
    const tools = createTools({ langgraph: lg });
    const out = await tools.searchKnowledgeBase.execute!({ query: 'what is LiteLLM?' }, opts());
    expect(lg.askCalls).toEqual(['what is LiteLLM?']);
    expect(out).toEqual({ answer: 'answer to: what is LiteLLM?', sourceIds: ['doc-1'] });
  });

  it('searchKnowledgeBase forwards the abort signal so a cancelled request cancels the lookup', async () => {
    let seen: AbortSignal | undefined;
    const lg = fakeLangGraph({
      async ask(_q, signal) {
        seen = signal;
        return { answer: 'x', sources: [] };
      },
    });
    const controller = new AbortController();
    await createTools({ langgraph: lg }).searchKnowledgeBase.execute!({ query: 'q' }, opts(controller.signal));
    expect(seen).toBe(controller.signal);
  });

  it('getCurrentTime formats in the requested zone (clock injected)', async () => {
    const tools = createTools({ langgraph: fakeLangGraph(), now: () => new Date('2026-10-10T23:30:00Z') });
    const out = (await tools.getCurrentTime.execute!({ timeZone: 'Asia/Kolkata' }, opts())) as { formatted: string };
    expect(out.formatted).toContain('Sunday, October 11, 2026'); // 23:30 UTC is already next day in IST
    expect(out.formatted).toContain('5:00:00 AM');
  });

  it('getCurrentTime throws on an unknown zone (the SDK reports it to the model as a tool error)', async () => {
    const tools = createTools({ langgraph: fakeLangGraph() });
    await expect(tools.getCurrentTime.execute!({ timeZone: 'Mars/Olympus' }, opts())).rejects.toThrow(RangeError);
  });
});
