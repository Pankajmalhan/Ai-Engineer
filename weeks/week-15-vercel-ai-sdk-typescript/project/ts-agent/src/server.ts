import { serve } from '@hono/node-server';
import { createApp } from './app';
import { loadConfig } from './config';
import { createLangGraphClient } from './langgraphClient';
import { createModel } from './models';

// Load ts-agent/.env if present (Node built-in; variables already set in the shell take precedence).
try {
  process.loadEnvFile();
} catch (error) {
  if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
}

const config = loadConfig();
const langgraph = createLangGraphClient({ baseUrl: config.langgraphUrl });

let selection;
if (config.mockModel) {
  const { createDemoModel } = await import('./demoModel');
  selection = { model: createDemoModel(), description: 'scripted demo model (MOCK_MODEL=1, no API calls)' };
} else {
  selection = createModel(config);
}

const app = createApp({ model: selection.model, langgraph });
serve({ fetch: app.fetch, port: config.port }, ({ port }) => {
  console.log(`agent layer on http://localhost:${port}`);
  console.log(`  model:     ${selection.description}`);
  console.log(`  langgraph: ${config.langgraphUrl}`);
  console.log('  POST /api/langgraph/stream  {"question": "..."}');
  console.log('  POST /api/agent             {"messages": [UIMessage]}');
});
