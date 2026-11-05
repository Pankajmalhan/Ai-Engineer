import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { createAssistantClient } from './assistantClient.js';
import { createServer } from './server.js';

const baseUrl = process.env.ASSISTANT_URL ?? 'http://localhost:8000';
const assistant = createAssistantClient({ baseUrl, timeoutMs: Number(process.env.ASSISTANT_TIMEOUT_MS ?? 30_000) });

// stdout carries the JSON-RPC stream -- anything else printed there corrupts the protocol. Log to stderr only.
console.error(`codebase-assistant MCP server on stdio -> ${baseUrl}`);

serveStdio(() => createServer(assistant));
