export default {
  async fetch(request, env) {
    if (!env.BRIGHTBEAN) {
      return new Response("BrightBean edge unavailable", { status: 503 });
    }

    const incoming = new URL(request.url);
    const target = new URL(`http://brightbean-edge${incoming.pathname}${incoming.search}`);
    const headers = new Headers(request.headers);
    const publicHost = request.headers.get("Host") || incoming.host;

    headers.delete("Host");
    headers.set("X-Forwarded-Host", publicHost);
    headers.set("X-Forwarded-Proto", "https");

    const init = {
      method: request.method,
      headers,
      redirect: "manual",
    };

    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }

    const method = request.method.toUpperCase();
    const readOnly = method === "GET" || method === "HEAD";
    const contentType = headers.get("Content-Type") || "";
    const contentLength = Number(headers.get("Content-Length") || "0");
    const retryableJsonWrite =
      !readOnly &&
      /^application\/([^;]+\+)?json(?:;|$)/i.test(contentType) &&
      Number.isFinite(contentLength) &&
      contentLength >= 0 &&
      contentLength <= 1024 * 1024;

    let retryBody;
    if (retryableJsonWrite) {
      retryBody = await request.clone().arrayBuffer();
    } else if (!readOnly) {
      init.body = request.body;
    }

    const maxAttempts = readOnly ? 3 : retryableJsonWrite ? 3 : 1;

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        const attemptInit = { ...init };
        if (retryBody !== undefined) {
          attemptInit.body = retryBody;
        }
        return await env.BRIGHTBEAN.fetch(new Request(target, attemptInit));
      } catch (error) {
        const handshakeTimeout =
          typeof error?.message === "string" &&
          /handshake timeout/i.test(error.message);

        if (handshakeTimeout && attempt < maxAttempts) {
          const delayMs = attempt === 1 ? 150 : 350;
          console.warn("BrightBean VPC handshake timeout; retrying bounded request", {
            attempt,
            method,
            retryableJsonWrite,
            delayMs,
          });
          await new Promise((resolve) => setTimeout(resolve, delayMs));
          continue;
        }

        console.error("BrightBean VPC fetch failed", error);
        return new Response("BrightBean edge unavailable", { status: 503 });
      }
    }

    return new Response("BrightBean edge unavailable", { status: 503 });
  },
};