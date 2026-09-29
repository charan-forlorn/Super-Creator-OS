export default {
  async fetch(request, env) {
    if (!env.BRIGHTBEAN) {
      return new Response("BrightBean edge unavailable", { status: 503 });
    }
    const incoming = new URL(request.url);
    const upstreamPath = incoming.pathname === "/"
      ? "/accounts/login/?next=/"
      : incoming.pathname + incoming.search;
    const target = new URL(`http://brightbean-edge${upstreamPath}`);
    const headers = new Headers(request.headers);
    headers.set("Host", "brightbean-edge");
    headers.set("X-Forwarded-Host", incoming.host);
    headers.set("X-Forwarded-Proto", "https");
    headers.set("X-Forwarded-Port", "443");
    const init = { method: request.method, headers, redirect: "manual" };
    if (request.method !== "GET" && request.method !== "HEAD") init.body = request.body;
    try {
      const upstream = await env.BRIGHTBEAN.fetch(new Request(target, init));
      return new Response(upstream.body, upstream);
    } catch (error) {
      console.error("BrightBean VPC fetch failed", error);
      return new Response("BrightBean edge unavailable", { status: 503 });
    }
  },
};