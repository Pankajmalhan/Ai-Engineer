import { describe, expect, it } from 'vitest';
import { BROWSER_TOOL_NAMES, MAX_SELECTION_CHARS, THEME_STORAGE_KEY, isBrowserTool, runClientTool, type BrowserEnv } from '../src/clientTools';

function fakeEnv(overrides: Partial<BrowserEnv> & { selected?: string } = {}) {
  const stored: Record<string, string> = {};
  const dataset: Record<string, string | undefined> = {};
  const env: BrowserEnv = {
    location: { href: 'http://localhost:5173/' },
    document: { title: 'Agent chat', documentElement: { lang: 'en', dataset } },
    navigator: { language: 'en-IN' },
    innerWidth: 1280,
    innerHeight: 720,
    getSelection: () => (overrides.selected === undefined ? null : { toString: () => overrides.selected! }),
    localStorage: { setItem: (k, v) => void (stored[k] = v) },
    ...overrides,
  };
  return { env, stored, dataset };
}

describe('getBrowserContext', () => {
  it('returns page facts and null when nothing is selected', () => {
    const { env } = fakeEnv();
    expect(runClientTool('getBrowserContext', {}, env)).toEqual({
      ok: true,
      output: { url: 'http://localhost:5173/', title: 'Agent chat', language: 'en-IN', viewport: { width: 1280, height: 720 }, selection: null },
    });
  });

  it('includes the trimmed selection', () => {
    const { env } = fakeEnv({ selected: '  some highlighted text \n' });
    const result = runClientTool('getBrowserContext', {}, env);
    expect(result).toMatchObject({ ok: true, output: { selection: 'some highlighted text' } });
  });

  it('caps a huge selection so a whole page is never sent to the model provider', () => {
    const { env } = fakeEnv({ selected: 'x'.repeat(5000) });
    const result = runClientTool('getBrowserContext', {}, env);
    expect(result.ok && (result.output as { selection: string }).selection.length).toBe(MAX_SELECTION_CHARS);
  });

  it('returns only the documented keys (no cookies, storage or DOM)', () => {
    const result = runClientTool('getBrowserContext', {}, fakeEnv().env);
    expect(result.ok && Object.keys(result.output as object).sort()).toEqual(['language', 'selection', 'title', 'url', 'viewport']);
  });
});

describe('setTheme', () => {
  it.each(['dark', 'light'] as const)('applies %s to the page and remembers it', (theme) => {
    const { env, stored, dataset } = fakeEnv();
    expect(runClientTool('setTheme', { theme }, env)).toEqual({ ok: true, output: { theme, applied: true } });
    expect(dataset.theme).toBe(theme);
    expect(stored[THEME_STORAGE_KEY]).toBe(theme);
  });

  it.each([{}, { theme: 'blue' }, { theme: 5 }, null, 'dark'])('rejects invalid model input %j without touching the page', (input) => {
    const { env, dataset } = fakeEnv();
    const result = runClientTool('setTheme', input, env);
    expect(result.ok).toBe(false);
    expect(dataset.theme).toBeUndefined();
  });

  it('still applies the theme when storage is blocked', () => {
    const { env, dataset } = fakeEnv({
      localStorage: { setItem: () => { throw new DOMException('blocked', 'SecurityError'); } },
    });
    expect(runClientTool('setTheme', { theme: 'dark' }, env)).toMatchObject({ ok: true });
    expect(dataset.theme).toBe('dark');
  });
});

describe('dispatch', () => {
  it('reports unknown tools as errors instead of throwing', () => {
    expect(runClientTool('deleteEverything', {}, fakeEnv().env)).toEqual({ ok: false, errorText: 'Unknown browser tool: deleteEverything' });
  });

  it('isBrowserTool recognises exactly the tools the server declares', () => {
    expect(BROWSER_TOOL_NAMES.every(isBrowserTool)).toBe(true);
    expect(isBrowserTool('searchKnowledgeBase')).toBe(false); // server-side tool: not ours to run
  });
});
