/**
 * Terminal client for the agent layer. Prints text the moment each delta arrives (no buffering),
 * so you can *see* streaming, and reports time-to-first-token vs total time.
 *
 *   npm run client -- "How does the AI SDK stream text?"                 # LangGraph pass-through
 *   npm run client -- --mode agent "What does LiteLLM do? "              # tool-calling agent
 *   npm run client -- --url http://localhost:3000 --mode agent "..."
 */
import { sseData } from './sse';

export type StreamStats = {
  text: string;
  textDeltas: number;
  /** ms from request start to the first text delta; undefined if no text arrived */
  firstTextMs?: number;
  totalMs: number;
  toolCalls: string[];
  errors: string[];
};

export type Handlers = {
  onText?: (delta: string) => void;
  onInfo?: (line: string) => void;
};

/** Reads an AI SDK UI message stream (SSE of JSON chunks) and reports what happened. */
export async function consumeUIMessageStream(
  response: Response,
  handlers: Handlers = {},
  startedAt = performance.now(),
): Promise<StreamStats> {
  if (!response.ok || !response.body) {
    throw new Error(`HTTP ${response.status}: ${await response.text().catch(() => '')}`);
  }
  const stats: StreamStats = { text: '', textDeltas: 0, totalMs: 0, toolCalls: [], errors: [] };
  for await (const data of sseData(response.body)) {
    if (data === '[DONE]') break;
    const chunk = JSON.parse(data) as { type: string; [k: string]: unknown };
    switch (chunk.type) {
      case 'text-delta': {
        const delta = String(chunk.delta ?? '');
        stats.firstTextMs ??= performance.now() - startedAt;
        stats.text += delta;
        stats.textDeltas += 1;
        handlers.onText?.(delta);
        break;
      }
      case 'data-step': {
        const step = chunk.data as { node: string; sources?: { id: string }[] };
        const ids = step.sources?.map((s) => s.id).join(', ');
        handlers.onInfo?.(`step: ${step.node}${ids ? ` -> sources [${ids}]` : ''}`);
        break;
      }
      case 'tool-input-available': {
        stats.toolCalls.push(String(chunk.toolName));
        handlers.onInfo?.(`tool call: ${String(chunk.toolName)}(${JSON.stringify(chunk.input)})`);
        break;
      }
      case 'tool-output-available':
        handlers.onInfo?.(`tool result: ${JSON.stringify(chunk.output)}`);
        break;
      case 'tool-output-error':
        handlers.onInfo?.(`tool error: ${String(chunk.errorText)}`);
        break;
      case 'error':
        stats.errors.push(String(chunk.errorText));
        handlers.onInfo?.(`error: ${String(chunk.errorText)}`);
        break;
    }
  }
  stats.totalMs = performance.now() - startedAt;
  return stats;
}

function parseArgs(argv: string[]) {
  let mode: 'langgraph' | 'agent' = 'langgraph';
  let url = process.env.AGENT_URL ?? 'http://localhost:3000';
  const words: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i]!;
    if (arg === '--mode') {
      const value = argv[++i];
      if (value !== 'langgraph' && value !== 'agent') throw new Error('--mode must be "langgraph" or "agent"');
      mode = value;
    } else if (arg === '--url') {
      url = argv[++i] ?? url;
    } else {
      words.push(arg);
    }
  }
  const question = words.join(' ').trim();
  if (!question) throw new Error('usage: npm run client -- [--mode langgraph|agent] [--url URL] "your question"');
  return { mode, url: url.replace(/\/$/, ''), question };
}

async function main() {
  const { mode, url, question } = parseArgs(process.argv.slice(2));
  const [path, body] =
    mode === 'langgraph'
      ? ['/api/langgraph/stream', { question }]
      : ['/api/agent', { messages: [{ id: 'm1', role: 'user', parts: [{ type: 'text', text: question }] }] }];

  const startedAt = performance.now();
  const response = await fetch(`${url}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });

  let midLine = false;
  const stats = await consumeUIMessageStream(
    response,
    {
      onText: (delta) => {
        process.stdout.write(delta);
        midLine = !delta.endsWith('\n');
      },
      onInfo: (line) => {
        if (midLine) process.stdout.write('\n');
        midLine = false;
        console.error(`\u001b[2m[${line}]\u001b[0m`);
      },
    },
    startedAt,
  );
  if (midLine) process.stdout.write('\n');
  const first = stats.firstTextMs === undefined ? 'n/a' : `${Math.round(stats.firstTextMs)}ms`;
  console.error(
    `\u001b[2m-- ${stats.textDeltas} text deltas | first text at ${first} | total ${Math.round(stats.totalMs)}ms | tools: ${stats.toolCalls.join(', ') || 'none'}\u001b[0m`,
  );
  if (stats.errors.length) process.exitCode = 1;
}

// Run only when executed directly (not when imported by tests).
if (process.argv[1] && import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exit(1);
  });
}
