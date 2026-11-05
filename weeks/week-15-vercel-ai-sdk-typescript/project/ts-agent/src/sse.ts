/**
 * Minimal Server-Sent Events reader: turns a byte stream into the `data:` payload of each event.
 *
 * Events are separated by a blank line. A chunk from the network can end in the middle of an
 * event (or in the middle of a UTF-8 character), so we buffer until we see the separator.
 * Lines starting with ":" are comments (keep-alives) and are ignored.
 */
export async function* sseData(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader();
  const decoder = new TextDecoder(); // { stream: true } keeps multi-byte characters split across chunks intact
  let buffer = '';
  const extract = (block: string): string | undefined => {
    const data = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''));
    return data.length ? data.join('\n') : undefined;
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      // normalise the whole buffer, so a \r\n split across two chunks still collapses
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
      let end: number;
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const data = extract(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (data !== undefined) yield data;
      }
    }
    const tail = extract(buffer);
    if (tail !== undefined) yield tail;
  } finally {
    // If the consumer stops early (break / abort), cancel so the upstream connection closes too.
    await reader.cancel().catch(() => {});
  }
}
