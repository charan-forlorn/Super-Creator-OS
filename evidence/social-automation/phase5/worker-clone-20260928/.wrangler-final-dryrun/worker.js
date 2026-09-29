// src/worker.mjs
var worker_default = {
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
      redirect: "manual"
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
    }
    try {
      return await env.BRIGHTBEAN.fetch(new Request(target, init));
    } catch (error) {
      console.error("BrightBean VPC fetch failed", error);
      return new Response("BrightBean edge unavailable", { status: 503 });
    }
  }
};
export {
  worker_default as default
};
//# sourceMappingURL=worker.js.map
