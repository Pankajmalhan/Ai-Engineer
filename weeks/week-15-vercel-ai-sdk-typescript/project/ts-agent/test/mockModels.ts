import { simulateReadableStream } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';

export const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 1, text: 1, reasoning: undefined },
};
export const stop = { unified: 'stop' as const, raw: undefined };
export const toolCallsFinish = { unified: 'tool-calls' as const, raw: undefined };

export const textStream = (...deltas: string[]) =>
  simulateReadableStream({
    chunks: [
      { type: 'text-start' as const, id: 't' },
      ...deltas.map((delta) => ({ type: 'text-delta' as const, id: 't', delta })),
      { type: 'text-end' as const, id: 't' },
      { type: 'finish' as const, finishReason: stop, usage },
    ],
  });

export const toolCallStream = (toolName: string, input: unknown, id = 'call-1') =>
  simulateReadableStream({
    chunks: [
      { type: 'tool-call' as const, toolCallId: id, toolName, input: JSON.stringify(input) },
      { type: 'finish' as const, finishReason: toolCallsFinish, usage },
    ],
  });

export const textModel = (id: string, ...deltas: string[]) =>
  new MockLanguageModelV4({
    modelId: id,
    doGenerate: async () => ({
      content: [{ type: 'text', text: deltas.join('') }],
      finishReason: stop,
      usage,
      warnings: [],
    }),
    doStream: async () => ({ stream: textStream(...deltas) }),
  });

export const failingModel = (id: string, error: unknown) =>
  new MockLanguageModelV4({
    modelId: id,
    doGenerate: async () => {
      throw error;
    },
    doStream: async () => {
      throw error;
    },
  });

/** Plays a list of scripted steps, one per model call (the last repeats if the loop goes on). */
export const scriptedModel = (steps: (() => ReturnType<typeof toolCallStream>)[]) => {
  let call = 0;
  return new MockLanguageModelV4({
    modelId: 'scripted',
    doStream: async () => ({ stream: steps[Math.min(call++, steps.length - 1)]!() }),
  });
};
