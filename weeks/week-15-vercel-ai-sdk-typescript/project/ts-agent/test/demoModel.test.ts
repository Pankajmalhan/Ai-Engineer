import { streamText } from 'ai';
import { describe, expect, it } from 'vitest';
import { createDemoModel } from '../src/demoModel';
import { clientTools, createTools } from '../src/tools';
import { fakeLangGraph } from './helpers';

const tools = { ...createTools({ langgraph: fakeLangGraph() }), ...clientTools };

async function firstCall(question: string) {
  const r = streamText({ model: createDemoModel(0), prompt: question, tools });
  const parts = [];
  for await (const p of r.stream) parts.push(p);
  return parts.find((p) => p.type === 'tool-call') as { toolName: string; input: unknown } | undefined;
}

describe('demo model tool choice', () => {
  it.each([
    ['Switch to dark theme', 'setTheme', { theme: 'dark' }],
    ['please use light mode theme', 'setTheme', { theme: 'light' }],
    ['What page am I on?', 'getBrowserContext', {}],
    ['what text did I select on the screen', 'getBrowserContext', {}],
    ['What does LiteLLM do?', 'searchKnowledgeBase', { query: 'What does LiteLLM do?' }],
  ])('%s -> %s', async (question, toolName, input) => {
    const call = await firstCall(question);
    expect(call?.toolName).toBe(toolName);
    expect(call?.input).toEqual(input);
  });
});
