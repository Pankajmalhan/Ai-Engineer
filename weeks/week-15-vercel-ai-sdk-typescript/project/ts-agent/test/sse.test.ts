import { describe, expect, it } from 'vitest';
import { sseData } from '../src/sse';
import { bodyFrom, collect, enc } from './helpers';

describe('sseData', () => {
  it('yields one payload per event', async () => {
    const { body } = bodyFrom(['data: a\n\ndata: b\n\n']);
    expect(await collect(sseData(body))).toEqual(['a', 'b']);
  });

  it('reassembles an event split across network chunks', async () => {
    const { body } = bodyFrom(['da', 'ta: {"x"', ':1}\n', '\ndata: two\n\n']);
    expect(await collect(sseData(body))).toEqual(['{"x":1}', 'two']);
  });

  it('handles CRLF line endings, even when \\r and \\n arrive in different chunks', async () => {
    const { body } = bodyFrom(['data: a\r', '\n\r\ndata: b\r\n\r\n']);
    expect(await collect(sseData(body))).toEqual(['a', 'b']);
  });

  it('joins multi-line data and ignores comments / other fields', async () => {
    const { body } = bodyFrom([': keep-alive\n\nevent: x\ndata: line1\ndata: line2\n\n']);
    expect(await collect(sseData(body))).toEqual(['line1\nline2']);
  });

  it('keeps a multi-byte character that is split across chunks intact', async () => {
    const bytes = enc.encode('data: €uro\n\n'); // "€" is 3 bytes
    const { body } = bodyFrom([bytes.slice(0, 7), bytes.slice(7)]); // cut inside the euro sign
    expect(await collect(sseData(body))).toEqual(['€uro']);
  });

  it('flushes a final event that has no trailing blank line', async () => {
    const { body } = bodyFrom(['data: last']);
    expect(await collect(sseData(body))).toEqual(['last']);
  });

  it('cancels the source when the consumer stops early (so the upstream connection closes)', async () => {
    const { body, state } = bodyFrom(['data: 1\n\n', 'data: 2\n\n', 'data: 3\n\n']);
    for await (const data of sseData(body)) {
      if (data === '1') break;
    }
    expect(state.cancelled).toBe(true);
  });
});
