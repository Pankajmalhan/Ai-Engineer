import type { LanguageModelV4Prompt } from '@ai-sdk/provider';
import { simulateReadableStream } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';

/**
 * Offline stand-in for a real model so the tool loop can be demoed with no API keys (MOCK_MODEL=1).
 * It is scripted, not intelligent: step 1 picks a tool from keywords in the user's question
 * (theme -> setTheme, page/browser/selection -> getBrowserContext, else searchKnowledgeBase);
 * once a tool result is in the prompt, step 2 streams a short answer built from that result.
 * Everything *around* it (tool validation, execution, the loop, streaming) is the real SDK.
 */
export function createDemoModel(tokenDelayMs = 40) {
  const usage = {
    inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
    outputTokens: { total: 1, text: 1, reasoning: undefined },
  };
  const lastUserText = (prompt: LanguageModelV4Prompt) => {
    for (const m of [...prompt].reverse()) {
      if (m.role !== 'user') continue;
      return m.content.map((p) => (p.type === 'text' ? p.text : '')).join('');
    }
    return '';
  };
  type ToolOutcome = { toolName: string; value: unknown };
  const lastToolOutcome = (prompt: LanguageModelV4Prompt): ToolOutcome | undefined => {
    const last = prompt[prompt.length - 1];
    if (last?.role !== 'tool') return undefined;
    const part = last.content.find((p) => p.type === 'tool-result');
    if (!part || part.type !== 'tool-result') return undefined;
    const out = part.output as { type: string; value?: unknown };
    return { toolName: part.toolName, value: out.type === 'json' || out.type === 'text' ? out.value : out };
  };

  const chooseTool = (question: string): { toolName: string; input: unknown } => {
    if (/\b(theme|dark|light)\b/i.test(question)) {
      const wantsLight = /\blight\b/i.test(question) && !/\bdark\b/i.test(question);
      return { toolName: 'setTheme', input: { theme: wantsLight ? 'light' : 'dark' } };
    }
    if (/\b(page|browser|tab|selected|selection|screen|viewport|url)\b/i.test(question)) {
      return { toolName: 'getBrowserContext', input: {} };
    }
    return { toolName: 'searchKnowledgeBase', input: { query: question } };
  };

  const describeOutcome = ({ toolName, value }: ToolOutcome): string => {
    const v = (value ?? {}) as Record<string, any>;
    if (toolName === 'setTheme') {
      return v.applied ? `Done. I switched the page to the ${v.theme} theme.` : `I couldn't change the theme: ${JSON.stringify(value)}`;
    }
    if (toolName === 'getBrowserContext') {
      const sel = v.selection ? ` You have selected: "${v.selection}".` : ' Nothing is selected.';
      return `You're on "${v.title}" (${v.url}), viewport ${v.viewport?.width}x${v.viewport?.height}, language ${v.language}.${sel}`;
    }
    return `Here is what the knowledge base says. ${typeof v.answer === 'string' ? v.answer : JSON.stringify(value)}`;
  };

  return new MockLanguageModelV4({
    provider: 'demo',
    modelId: 'scripted-demo',
    doStream: async ({ prompt }) => {
      const outcome = lastToolOutcome(prompt);
      if (outcome === undefined) {
        const { toolName, input } = chooseTool(lastUserText(prompt));
        return {
          stream: simulateReadableStream({
            initialDelayInMs: tokenDelayMs,
            chunkDelayInMs: null,
            chunks: [
              {
                type: 'tool-call' as const,
                toolCallId: 'demo-call-1',
                toolName,
                input: JSON.stringify(input),
              },
              { type: 'finish' as const, finishReason: { unified: 'tool-calls' as const, raw: undefined }, usage },
            ],
          }),
        };
      }
      const words = describeOutcome(outcome).match(/\S+\s*/g) ?? [];
      return {
        stream: simulateReadableStream({
          initialDelayInMs: tokenDelayMs,
          chunkDelayInMs: tokenDelayMs,
          chunks: [
            { type: 'text-start' as const, id: 'demo-text' },
            ...words.map((delta) => ({ type: 'text-delta' as const, id: 'demo-text', delta })),
            { type: 'text-end' as const, id: 'demo-text' },
            { type: 'finish' as const, finishReason: { unified: 'stop' as const, raw: undefined }, usage },
          ],
        }),
      };
    },
  });
}
