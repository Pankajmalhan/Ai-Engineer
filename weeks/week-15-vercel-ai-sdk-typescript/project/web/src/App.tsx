import { useChat } from '@ai-sdk/react';
import { DefaultChatTransport, getToolName, isToolUIPart, lastAssistantMessageIsCompleteWithToolCalls } from 'ai';
import { useState } from 'react';
import { isBrowserTool, runClientTool } from './clientTools';

const SUGGESTIONS = [
  { label: 'What page am I on?', hint: 'runs in your browser' },
  { label: 'Switch to dark theme', hint: 'changes this page' },
  { label: 'What does LiteLLM do?', hint: 'runs on the server, asks Python' },
];

export function App() {
  const [input, setInput] = useState('');

  const { messages, sendMessage, addToolOutput, status, error, stop } = useChat({
    // The TypeScript agent layer (proxied by Vite in dev). The model, its API key and the
    // server-side tools all live there -- never in this bundle.
    transport: new DefaultChatTransport({ api: '/api/agent' }),

    // When every tool call in the last assistant message has an output, send the conversation back
    // automatically so the model can continue. Without this the chat would stall after a browser tool.
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls,

    // Called when the model asks for a tool. Tools we recognise run right here, in the page.
    // (Server-side tools arrive already executed, so we ignore anything that isn't ours.)
    onToolCall: ({ toolCall }) => {
      if (toolCall.dynamic || !isBrowserTool(toolCall.toolName)) return;
      const result = runClientTool(toolCall.toolName, toolCall.input, window);
      // Deliberately not awaited: awaiting addToolOutput inside onToolCall can deadlock the chat.
      if (result.ok) {
        addToolOutput({ tool: toolCall.toolName, toolCallId: toolCall.toolCallId, output: result.output });
      } else {
        addToolOutput({ tool: toolCall.toolName, toolCallId: toolCall.toolCallId, state: 'output-error', errorText: result.errorText });
      }
    },
  });

  const busy = status === 'submitted' || status === 'streaming';
  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    sendMessage({ text: trimmed });
    setInput('');
  };

  return (
    <main className="app">
      <header>
        <h1>Agent chat</h1>
        <p>
          A TypeScript agent (Vercel AI SDK) with tools that run <b>in this page</b>, tools that run on the server, and a Python
          LangGraph service behind it.
        </p>
      </header>

      <section className="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s.label} type="button" onClick={() => send(s.label)}>
                {s.label}
                <small>{s.hint}</small>
              </button>
            ))}
          </div>
        )}

        {messages.map((message) => (
          <article key={message.id} className={`msg ${message.role}`}>
            {message.parts.map((part, i) => {
              if (part.type === 'text') return <p key={i}>{part.text}</p>;
              if (isToolUIPart(part)) {
                const name = getToolName(part);
                return (
                  <details key={i} className={`tool ${part.state}`} open={part.state === 'output-error'}>
                    <summary>
                      <span className={`where ${isBrowserTool(name) ? 'browser' : 'server'}`}>{isBrowserTool(name) ? 'browser' : 'server'}</span>
                      <code>{name}</code>
                      <span className="state">{part.state === 'output-available' ? 'done' : part.state === 'output-error' ? 'failed' : 'running…'}</span>
                    </summary>
                    <pre>{JSON.stringify({ input: part.input, ...(part.state === 'output-available' ? { output: part.output } : {}), ...(part.state === 'output-error' ? { error: part.errorText } : {}) }, null, 2)}</pre>
                  </details>
                );
              }
              return null;
            })}
          </article>
        ))}

        {status === 'submitted' && <p className="status">Thinking…</p>}
        {error && <p className="error" role="alert">Request failed: {error.message}</p>}
      </section>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask something…" aria-label="Message" autoFocus />
        {busy ? (
          <button type="button" onClick={() => stop()}>Stop</button>
        ) : (
          <button type="submit" disabled={!input.trim()}>Send</button>
        )}
      </form>
    </main>
  );
}
