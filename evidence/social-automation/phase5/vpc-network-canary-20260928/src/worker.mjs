export default {
  async fetch(request, env) {
    try {
      const incoming = new URL(request.url);
      const target = new URL(`http://172.18.0.6${incoming.pathname}${incoming.search}`);
      const headers = new Headers(request.headers);
      headers.delete("Host");
      headers.set("X-Forwarded-Proto", "https");
      return await env.PRIVATE_NETWORK.fetch(new Request(target, {
        method: request.method,
        headers,
        redirect: "manual",
        body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      }));
    } catch (error) {
      console.error("VPC Network canary failure", {
        name: error?.name ?? null,
        message: error?.message ?? null,
        code: error?.code ?? null,
        remote: error?.remote ?? null,
      });
      return new Response("VPC Network canary unavailable", { status: 503 });
    }
  },
};
