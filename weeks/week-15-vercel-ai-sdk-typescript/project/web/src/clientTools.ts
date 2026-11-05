import { z } from 'zod';

/**
 * Tools that run IN THE BROWSER. The server declares them (ts-agent/src/tools.ts `clientTools`,
 * no `execute`); when the model calls one, the page runs it here and sends the result back.
 *
 * The model's tool input is untrusted -- it is text a model produced -- so every tool validates its
 * input before touching the page. Results go to the model provider, so what we return is a
 * deliberate, small, privacy-conscious subset (selection is capped; no cookies, storage or DOM dump).
 */

/** The slice of `window` the tools need, so tests can pass a plain object instead of a browser. */
export interface BrowserEnv {
  location: { href: string };
  document: { title: string; documentElement: { lang: string; dataset: Record<string, string | undefined> } };
  navigator: { language: string };
  innerWidth: number;
  innerHeight: number;
  getSelection(): { toString(): string } | null;
  localStorage?: { setItem(key: string, value: string): void };
}

export const BROWSER_TOOL_NAMES = ['getBrowserContext', 'setTheme'] as const;
export type BrowserToolName = (typeof BROWSER_TOOL_NAMES)[number];
export const isBrowserTool = (name: string): name is BrowserToolName => (BROWSER_TOOL_NAMES as readonly string[]).includes(name);

export const THEME_STORAGE_KEY = 'agent-chat-theme';
export const MAX_SELECTION_CHARS = 500;

export type ClientToolResult = { ok: true; output: unknown } | { ok: false; errorText: string };

const themeInput = z.object({ theme: z.enum(['light', 'dark']) });

export function runClientTool(name: string, input: unknown, env: BrowserEnv): ClientToolResult {
  switch (name) {
    case 'getBrowserContext': {
      const selected = env.getSelection()?.toString().trim() ?? '';
      return {
        ok: true,
        output: {
          url: env.location.href,
          title: env.document.title,
          language: env.navigator.language,
          viewport: { width: env.innerWidth, height: env.innerHeight },
          selection: selected ? selected.slice(0, MAX_SELECTION_CHARS) : null,
        },
      };
    }
    case 'setTheme': {
      const parsed = themeInput.safeParse(input);
      if (!parsed.success) return { ok: false, errorText: "Invalid input: theme must be 'light' or 'dark'." };
      env.document.documentElement.dataset.theme = parsed.data.theme;
      try {
        env.localStorage?.setItem(THEME_STORAGE_KEY, parsed.data.theme); // remembering it is best-effort
      } catch {
        /* storage blocked (private mode etc.): the theme still applies for this session */
      }
      return { ok: true, output: { theme: parsed.data.theme, applied: true } };
    }
    default:
      return { ok: false, errorText: `Unknown browser tool: ${name}` };
  }
}
