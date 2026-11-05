import { describe, expect, it } from 'vitest';
import { loadConfig } from '../src/config';

describe('loadConfig', () => {
  it('uses documented defaults', () => {
    const c = loadConfig({});
    expect(c).toMatchObject({
      openaiModel: 'gpt-4o-mini',
      fallbackModel: 'gpt-4o',
      litellmBaseUrl: 'http://localhost:4000/v1',
      langgraphUrl: 'http://localhost:8000',
      mockModel: false,
      port: 3000,
    });
    expect(c.openaiApiKey).toBeUndefined();
  });

  it('treats empty strings (as in a copied .env) like unset', () => {
    expect(loadConfig({ OPENAI_API_KEY: '', PORT: '' }).openaiApiKey).toBeUndefined();
    expect(loadConfig({ PORT: '' }).port).toBe(3000);
  });

  it('reads overrides and coerces the port', () => {
    const c = loadConfig({ PORT: '4010', MOCK_MODEL: '1', FALLBACK_MODEL: 'gpt-4o-mini' });
    expect(c).toMatchObject({ port: 4010, mockModel: true, fallbackModel: 'gpt-4o-mini' });
  });

  it('fails fast on a malformed URL', () => {
    expect(() => loadConfig({ LANGGRAPH_URL: 'not a url' })).toThrow();
  });
});
