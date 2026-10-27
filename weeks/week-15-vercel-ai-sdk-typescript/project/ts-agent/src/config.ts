import { z } from 'zod';

const emptyToUndefined = (v: unknown) => (v === '' ? undefined : v);

const schema = z.object({
  OPENAI_API_KEY: z.preprocess(emptyToUndefined, z.string().optional()),
  OPENAI_MODEL: z.preprocess(emptyToUndefined, z.string().default('gpt-4o-mini')),
  LITELLM_BASE_URL: z.preprocess(emptyToUndefined, z.string().url().default('http://localhost:4000/v1')),
  LITELLM_API_KEY: z.preprocess(emptyToUndefined, z.string().optional()),
  FALLBACK_MODEL: z.preprocess(emptyToUndefined, z.string().default('gpt-4o')),
  LANGGRAPH_URL: z.preprocess(emptyToUndefined, z.string().url().default('http://localhost:8000')),
  MOCK_MODEL: z.preprocess(emptyToUndefined, z.enum(['0', '1']).default('0')),
  PORT: z.preprocess(emptyToUndefined, z.coerce.number().int().positive().default(3000)),
});

export type Config = {
  openaiApiKey?: string;
  openaiModel: string;
  litellmBaseUrl: string;
  litellmApiKey?: string;
  fallbackModel: string;
  langgraphUrl: string;
  mockModel: boolean;
  port: number;
};

export function loadConfig(env: Record<string, string | undefined> = process.env): Config {
  const e = schema.parse(env);
  return {
    openaiApiKey: e.OPENAI_API_KEY,
    openaiModel: e.OPENAI_MODEL,
    litellmBaseUrl: e.LITELLM_BASE_URL,
    litellmApiKey: e.LITELLM_API_KEY,
    fallbackModel: e.FALLBACK_MODEL,
    langgraphUrl: e.LANGGRAPH_URL,
    mockModel: e.MOCK_MODEL === '1',
    port: e.PORT,
  };
}
