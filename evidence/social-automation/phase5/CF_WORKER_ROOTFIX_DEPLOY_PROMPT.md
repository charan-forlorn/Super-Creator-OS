/goal /x10
Deploy the verified BrightBean Worker root-handler fix now. Cloudflare MCP OAuth is already authorized for the current Hermes process. Execute the real Cloudflare MCP mutations; do not merely explain them.

Account ID: cb98ff5a98ddb6c0f09450505be7c3f5
Worker script: brightbean-social-edge-20260928
VPC binding: BRIGHTBEAN -> service_id 01a0e4c6-ae62-74e0-8cbf-4df204bec536

Use ONLY these Cloudflare MCP tools:
1) mcp__cloudflare__post_accounts_workers_scripts_versions
2) mcp__cloudflare__post_accounts_workers_scripts_deployments
3) mcp__cloudflare__post_accounts_workers_scripts_subdomain
4) mcp__cloudflare__get_accounts_workers_scripts_subdomain
5) mcp__cloudflare__get_accounts_workers_scripts_versions

For tool 1, upload EXACTLY one module worker.mjs with this source:

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

Multipart parameters for tool 1:
content_type = multipart/form-data; boundary=----HermesBrightBeanRootFix20260928
body = exact CRLF multipart with two parts:
------HermesBrightBeanRootFix20260928
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"main_module":"worker.mjs","bindings":[{"name":"BRIGHTBEAN","type":"vpc_service","service_id":"01a0e4c6-ae62-74e0-8cbf-4df204bec536"}],"compatibility_date":"2026-09-28","annotations":{"workers/message":"BrightBean stable public edge root-handler fix","workers/tag":"brightbean-vpc-edge-rootfix-20260928"}}
------HermesBrightBeanRootFix20260928
Content-Disposition: form-data; name="worker.mjs"; filename="worker.mjs"
Content-Type: application/javascript+module

[the exact source above]
------HermesBrightBeanRootFix20260928--

Call tool 1 with script_name=brightbean-social-edge-20260928, content_type above, and exact body. Capture version_id. Stop on upload validation error and report it exactly.

Then call tool 2 with script_name=brightbean-social-edge-20260928 and body {"strategy":"percentage","versions":[{"percentage":100,"version_id":"<VERSION_ID>"}]} to make the new version active. Capture deployment id.

Then call tool 3 with script_name=brightbean-social-edge-20260928 and body {"enabled":true,"previews_enabled":false}.

Then call tool 4 and tool 5 read-only to confirm the subdomain is enabled and the new version is active/latest. Do not create DNS. Do not touch the named tunnel or Woodpecker.

Return only compact verification: version_id, deployment_id, active/latest version, workers.dev enabled, previews_enabled.