export class AssistantStreamError extends Error {
  constructor(
    message: string,
    public status = 502,
  ) {
    super(message);
  }
}

// The stream carries retrieval metadata first and the same validated JSON reply
// last. It is private to this request; it never uses shared workspace SSE events.
export async function readAssistantReply(
  response: Response,
  onRetrieval: (event: { revision: number; retrieval: unknown }) => void,
): Promise<any> {
  if (
    !response.ok ||
    !response.headers.get("Content-Type")?.includes("application/x-ndjson")
  )
    return response.json();
  if (!response.body)
    throw new AssistantStreamError(
      "The assistant response was interrupted. Try again.",
    );
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "",
    bytes = 0,
    reply: unknown,
    retrieved = false,
    ended = false;
  const consume = (line: string) => {
    if (!line.trim()) return;
    if (ended)
      throw new AssistantStreamError("The assistant sent an invalid response.");
    const event = JSON.parse(line);
    if (event.type === "retrieval" && !retrieved) {
      retrieved = true;
      onRetrieval(event);
    } else if (
      event.type === "answer" &&
      retrieved &&
      event.data &&
      typeof event.data === "object"
    ) {
      ended = true;
      reply = event.data;
    } else if (event.type === "error") {
      throw new AssistantStreamError(
        typeof event.detail === "string"
          ? event.detail
          : "The assistant could not answer. Try again.",
        Number.isInteger(event.status) ? event.status : 502,
      );
    } else
      throw new AssistantStreamError("The assistant sent an invalid response.");
  };
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 8000000)
        throw new AssistantStreamError("The assistant response is too large.");
      buffer += decoder.decode(value, { stream: true });
      let newline;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        if (newline > 4000000)
          throw new AssistantStreamError(
            "The assistant response is too large.",
          );
        consume(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (buffer.length > 4000000)
        throw new AssistantStreamError("The assistant response is too large.");
    }
    buffer += decoder.decode();
    if (buffer.trim()) consume(buffer);
    if (!ended)
      throw new AssistantStreamError(
        "The assistant response was interrupted. Try again.",
      );
    return reply;
  } catch (error) {
    if (error instanceof SyntaxError || error instanceof TypeError)
      throw new AssistantStreamError("The assistant sent an invalid response.");
    throw error;
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
