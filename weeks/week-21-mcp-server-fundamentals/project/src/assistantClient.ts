import * as z from 'zod/v4';

/** Shape returned by the Python assistant's `POST /v1/ask` (see week-15 python-service). */
const AskResponse = z.object({
    answer: z.string(),
    sources: z.array(z.string()).default([])
});

export type AskResult = z.infer<typeof AskResponse>;

export class AssistantError extends Error {
    constructor(
        message: string,
        readonly kind: 'unreachable' | 'timeout' | 'http' | 'bad-response'
    ) {
        super(message);
        this.name = 'AssistantError';
    }
}

export interface AssistantClientOptions {
    baseUrl: string;
    timeoutMs?: number;
    /** Injected in tests; defaults to the global fetch. */
    fetch?: typeof fetch;
}

export interface AssistantClient {
    ask(question: string, signal?: AbortSignal): Promise<AskResult>;
}

export function createAssistantClient(options: AssistantClientOptions): AssistantClient {
    const { baseUrl, timeoutMs = 30_000, fetch: doFetch = fetch } = options;
    const url = new URL('/v1/ask', baseUrl);

    return {
        async ask(question, signal) {
            const timeout = AbortSignal.timeout(timeoutMs);
            let res: Response;
            try {
                res = await doFetch(url, {
                    method: 'POST',
                    headers: { 'content-type': 'application/json' },
                    body: JSON.stringify({ question }),
                    // aborts on our timeout OR when the MCP client cancels the tool call
                    signal: signal ? AbortSignal.any([signal, timeout]) : timeout
                });
            } catch (err) {
                if (timeout.aborted) throw new AssistantError(`assistant did not answer within ${timeoutMs} ms`, 'timeout');
                if (signal?.aborted) throw err;
                throw new AssistantError(`cannot reach assistant at ${url.origin}: ${(err as Error).message}`, 'unreachable');
            }

            if (!res.ok) {
                const detail = (await res.text().catch(() => '')).slice(0, 200);
                throw new AssistantError(`assistant returned HTTP ${res.status}${detail ? `: ${detail}` : ''}`, 'http');
            }

            const parsed = AskResponse.safeParse(await res.json().catch(() => undefined));
            if (!parsed.success) {
                throw new AssistantError('assistant returned a body that is not {answer, sources}', 'bad-response');
            }
            return parsed.data;
        }
    };
}
