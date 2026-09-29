const enc = new TextEncoder();
const dec = new TextDecoder();

function timeout(ms) {
  return new Promise((_, reject) => setTimeout(() => reject(new Error("socket_read_timeout")), ms));
}

async function readSome(socket) {
  const reader = socket.readable.getReader();
  try {
    const first = await Promise.race([reader.read(), timeout(5000)]);
    if (first.done) return new Uint8Array();
    return first.value;
  } finally {
    try { reader.releaseLock(); } catch {}
  }
}

export default {
  async fetch(request, env) {
    let socket;
    try {
      const incoming = new URL(request.url);
      socket = await env.PRIVATE_NETWORK.connect("172.18.0.6:80");
      const writer = socket.writable.getWriter();
      const path = incoming.pathname + incoming.search;
      const host = "brightbean-edge";
      const lines = [
        `${request.method} ${path} HTTP/1.1`,
        `Host: ${host}`,
        "Connection: close",
        "X-Forwarded-Proto: https",
        "X-Forwarded-Host: brightbean-edge",
      ];
      if (request.method !== "GET" && request.method !== "HEAD") {
        const body = new Uint8Array(await request.arrayBuffer());
        lines.push(`Content-Length: ${body.byteLength}`);
        lines.push("Content-Type: application/octet-stream");
        await writer.write(enc.encode(lines.join("\r\n") + "\r\n\r\n"));
        if (body.byteLength) await writer.write(body);
      } else {
        await writer.write(enc.encode(lines.join("\r\n") + "\r\n\r\n"));
      }
      await writer.close();

      const bytes = await readSome(socket);
      const text = dec.decode(bytes);
      const sep = text.indexOf("\r\n\r\n");
      if (sep < 0) throw new Error("invalid_http_response");
      const head = text.slice(0, sep);
      const statusMatch = head.match(/^HTTP\/\d(?:\.\d)?\s+(\d+)/);
      const status = statusMatch ? Number(statusMatch[1]) : 502;
      const headerLines = head.split("\r\n").slice(1);
      const responseHeaders = new Headers();
      for (const line of headerLines) {
        const i = line.indexOf(":");
        if (i > 0) responseHeaders.set(line.slice(0, i).trim(), line.slice(i + 1).trim());
      }
      const bodyText = text.slice(sep + 4);
      return new Response(bodyText, { status, headers: responseHeaders });
    } catch (error) {
      console.error("VPC connect canary failure", {
        name: error?.name ?? null,
        message: error?.message ?? null,
      });
      return new Response("VPC connect canary unavailable", { status: 503 });
    } finally {
      try { socket?.close(); } catch {}
    }
  },
};
