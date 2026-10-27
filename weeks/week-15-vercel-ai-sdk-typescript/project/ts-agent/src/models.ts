import { createOpenAI } from '@ai-sdk/openai';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import type { LanguageModelV4, LanguageModelV4Middleware } from '@ai-sdk/provider';
import { wrapLanguageModel } from 'ai';
import type { Config } from './config';

function isAbort(error: unknown, params: { abortSignal?: AbortSignal }): boolean {
  return params.abortSignal?.aborted === true || (error instanceof Error && error.name === 'AbortError');
}

/**
 * Wraps `primary` so that if *starting* a call fails (HTTP 4xx/5xx, network error, provider
 * outage) the same request is sent to `fallback` instead.
 *
 * Deliberate limits:
 *  - Only failures before the first token trigger the fallback. If the primary dies mid-stream we
 *    let the error surface: restarting on another model would emit a second, different answer
 *    after the user has already seen partial text.
 *  - Client aborts are never "failures" -- they are re-thrown so we don't spend a fallback call
 *    on a request nobody is waiting for.
 *  - This fires on the first error, before the SDK's own retry loop (maxRetries) gets a second
 *    try at the primary. That favours latency; pass `maxRetries` to streamText and move this
 *    wrapper to the retry layer if you prefer retrying the primary first.
 */
export function withFallback(
  primary: LanguageModelV4,
  fallback: LanguageModelV4,
  onFallback?: (error: unknown) => void,
): LanguageModelV4 {
  const middleware: LanguageModelV4Middleware = {
    specificationVersion: 'v4',
    wrapGenerate: async ({ doGenerate, params }) => {
      try {
        return await doGenerate();
      } catch (error) {
        if (isAbort(error, params)) throw error;
        onFallback?.(error);
        return fallback.doGenerate(params);
      }
    },
    wrapStream: async ({ doStream, params }) => {
      try {
        return await doStream();
      } catch (error) {
        if (isAbort(error, params)) throw error;
        onFallback?.(error);
        return fallback.doStream(params);
      }
    },
  };
  return wrapLanguageModel({ model: primary, middleware });
}

export type ModelSelection = {
  model: LanguageModelV4;
  /** Human-readable description for startup logs. */
  description: string;
};

/**
 * Primary: OpenAI, called directly through @ai-sdk/openai with OPENAI_API_KEY.
 * Optional fallback: a second model served by a LiteLLM proxy, which speaks the OpenAI
 * chat-completions protocol, so the generic OpenAI-compatible provider is all the SDK needs (just a
 * baseURL). The fallback only exists if LITELLM_API_KEY is set; otherwise OpenAI runs alone.
 * (LiteLLM alone also works: no OpenAI key => the proxy model is used directly.)
 */
export function createModel(
  config: Config,
  onFallback: (error: unknown) => void = (e) =>
    console.warn(`[models] primary failed, using fallback: ${e instanceof Error ? e.message : String(e)}`),
): ModelSelection {
  const primary = config.openaiApiKey
    ? createOpenAI({ apiKey: config.openaiApiKey })(config.openaiModel)
    : undefined;
  const fallback = config.litellmApiKey
    ? createOpenAICompatible({
        name: 'litellm',
        baseURL: config.litellmBaseUrl,
        apiKey: config.litellmApiKey,
      }).chatModel(config.fallbackModel)
    : undefined;

  if (primary && fallback) {
    return {
      model: withFallback(primary, fallback, onFallback),
      description: `${config.openaiModel} via OpenAI (fallback: ${config.fallbackModel} via LiteLLM)`,
    };
  }
  if (primary) return { model: primary, description: `${config.openaiModel} via OpenAI (no fallback: LITELLM_API_KEY unset)` };
  if (fallback) return { model: fallback, description: `${config.fallbackModel} via LiteLLM only (OPENAI_API_KEY unset)` };
  throw new Error('No model configured: set OPENAI_API_KEY (and optionally LITELLM_API_KEY for a fallback) in .env, or MOCK_MODEL=1 for the offline demo.');
}
