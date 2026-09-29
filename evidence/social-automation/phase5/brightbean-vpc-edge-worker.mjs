export default {
  async fetch(request, env) {
    if (!env.BRIGHTBEAN) {
      return new Response("BrightBean VPC binding unavailable", { status: 503 });
    }

    const headers = new Headers(request.headers);
    headers.set("X-Forwarded-Proto", "https");

    const clientIp = request.headers.get("CF-Connecting-IP");
    if (clientIp) headers.set("X-Forwarded-For", clientIp);

    const proxied = new Request(request, { headers });
    return env.BRIGHTBEAN.fetch(proxied);
  },
};