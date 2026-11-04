/**
 * Stand-in for the Python FastAPI assistant (same `POST /v1/ask` contract) so the MCP server can be
 * exercised end to end without Python, an LLM, or API keys. Used by `npm run fake-assistant` and the
 * stdio end-to-end test.
 */
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';

export function startFakeAssistant(port = 0): Promise<{ server: Server; url: string; questions: string[] }> {
    const questions: string[] = [];
    const server = createServer((req, res) => {
        if (req.method !== 'POST' || req.url !== '/v1/ask') {
            res.writeHead(404).end();
            return;
        }
        let body = '';
        req.on('data', chunk => (body += chunk));
        req.on('end', () => {
            const { question } = JSON.parse(body) as { question: string };
            questions.push(question);
            if (question.includes('boom')) {
                res.writeHead(500, { 'content-type': 'text/plain' }).end('upstream exploded');
                return;
            }
            res.writeHead(200, { 'content-type': 'application/json' });
            res.end(JSON.stringify({ answer: `Fake answer to: ${question}`, sources: ['src/router.ts', 'src/auth/session.ts'] }));
        });
    });
    return new Promise(resolve => {
        server.listen(port, '127.0.0.1', () => {
            resolve({ server, url: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, questions });
        });
    });
}

if (import.meta.url === `file://${process.argv[1]}`) {
    const { url } = await startFakeAssistant(Number(process.env.PORT ?? 8000));
    console.error(`fake assistant listening on ${url}`);
}
