import { APICallError, generateText, streamText } from 'ai';
import { describe, expect, it, vi } from 'vitest';
import { loadConfig } from '../src/config';
import { createModel, withFallback } from '../src/models';
import { failingModel, textModel, usage } from './mockModels';
import { MockLanguageModelV4 } from 'ai/test';
import { simulateReadableStream } from 'ai';

const outage = () =>
  new APICallError({ message: 'overloaded', url: 'https://api.openai.com', requestBodyValues: {}, statusCode: 503, isRetryable: true });

describe('withFallback', () => {
  it('does not touch the fallback when the primary works', async () => {
    const primary = textModel('gpt-4o-mini', 'from primary');
    const fallback = textModel('gpt-4o', 'from fallback');
    const onFallback = vi.fn();
    const { text } = await generateText({ model: withFallback(primary, fallback, onFallback), prompt: 'hi' });
    expect(text).toBe('from primary');
    expect(fallback.doGenerateCalls).toHaveLength(0);
    expect(onFallback).not.toHaveBeenCalled();
  });

  it('generate: retries the same request on the fallback when the primary fails', async () => {
    const primary = failingModel('gpt-4o-mini', outage());
    const fallback = textModel('gpt-4o', 'from fallback');
    const onFallback = vi.fn();
    const { text } = await generateText({ model: withFallback(primary, fallback, onFallback), prompt: 'hi', maxRetries: 0 });
    expect(text).toBe('from fallback');
    expect(onFallback).toHaveBeenCalledOnce();
    // same prompt reached the fallback
    expect(JSON.stringify(fallback.doGenerateCalls[0]!.prompt)).toContain('hi');
  });

  it('stream: falls back when the primary cannot start streaming', async () => {
    const primary = failingModel('gpt-4o-mini', outage());
    const fallback = textModel('gpt-4o', 'Hello ', 'fallback');
    const result = streamText({ model: withFallback(primary, fallback), prompt: 'hi', maxRetries: 0 });
    expect(await result.text).toBe('Hello fallback');
    expect(fallback.doStreamCalls).toHaveLength(1);
  });

  it('surfaces the fallback error when both providers fail', async () => {
    const model = withFallback(failingModel('gpt-4o-mini', outage()), failingModel('gpt-4o', new Error('litellm down')));
    await expect(generateText({ model, prompt: 'hi', maxRetries: 0 })).rejects.toThrow('litellm down');
  });

  it('does not use the fallback for a client abort', async () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    const fallback = textModel('gpt-4o', 'x');
    const model = withFallback(failingModel('gpt-4o-mini', abort), fallback);
    await expect(generateText({ model, prompt: 'hi', maxRetries: 0 })).rejects.toThrow();
    expect(fallback.doGenerateCalls).toHaveLength(0);
  });

  it('does NOT restart on the fallback if the primary fails mid-stream (no duplicated answer)', async () => {
    const primary = new MockLanguageModelV4({
      modelId: 'gpt-4o-mini',
      doStream: async () => ({
        stream: simulateReadableStream({
          chunks: [
            { type: 'text-start' as const, id: 't' },
            { type: 'text-delta' as const, id: 't', delta: 'partial ' },
            { type: 'error' as const, error: new Error('connection reset') },
            { type: 'finish' as const, finishReason: { unified: 'error' as const, raw: undefined }, usage },
          ],
        }),
      }),
    });
    const fallback = textModel('gpt-4o', 'a second, different answer');
    const parts: string[] = [];
    const result = streamText({ model: withFallback(primary, fallback), prompt: 'hi', maxRetries: 0, onError: () => {} });
    for await (const part of result.stream) parts.push(part.type);
    expect(parts).toContain('error');
    expect(fallback.doStreamCalls).toHaveLength(0);
  });
});

describe('createModel (provider configuration)', () => {
  it('wires OpenAI primary + LiteLLM fallback when both keys exist', () => {
    const { model, description } = createModel(loadConfig({ OPENAI_API_KEY: 'a', LITELLM_API_KEY: 'l' }));
    expect(model.provider).toContain('openai');
    expect(model.modelId).toBe('gpt-4o-mini');
    expect(description).toContain('fallback: gpt-4o via LiteLLM');
  });

  it('uses OpenAI alone, or LiteLLM alone, when only one is configured', () => {
    expect(createModel(loadConfig({ OPENAI_API_KEY: 'a' })).description).toContain('no fallback');
    expect(createModel(loadConfig({ OPENAI_API_KEY: 'a', OPENAI_MODEL: 'gpt-4o' })).model.modelId).toBe('gpt-4o');
    const only = createModel(loadConfig({ LITELLM_API_KEY: 'l', FALLBACK_MODEL: 'gpt-4o-mini' }));
    expect(only.model.modelId).toBe('gpt-4o-mini');
    expect(only.model.provider).toContain('litellm');
  });

  it('refuses to start with no provider, and says what to set', () => {
    expect(() => createModel(loadConfig({}))).toThrow(/OPENAI_API_KEY.*LITELLM_API_KEY/s);
  });
});
