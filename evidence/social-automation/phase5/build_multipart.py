from pathlib import Path
import json, hashlib
boundary = '----BBVPC20260928'
metadata = {
    'main_module': 'worker.mjs',
    'bindings': [{'type':'vpc_service','name':'BRIGHTBEAN','service_id':'01a0e4c6-ae62-74e0-8cbf-4df204bec536'}],
    'compatibility_date': '2026-09-28',
    'annotations': {'workers/message':'BrightBean VPC edge','workers/tag':'bb-vpc-20260928'},
}
worker = '''export default {
  async fetch(request, env) {
    try {
      const u = new URL(request.url);
      const h = new Headers(request.headers);
      h.set("host", "brightbean-edge");
      h.set("x-forwarded-proto", "https");
      h.set("x-forwarded-host", u.host);
      const init = { method: request.method, headers: h };
      if (request.method !== "GET" && request.method !== "HEAD") init.body = request.body;
      const r = await env.BRIGHTBEAN.fetch(new Request("http://brightbean-edge" + u.pathname + u.search, init));
      return new Response(r.body, r);
    } catch (e) {
      return new Response("BrightBean edge unavailable", { status: 503 });
    }
  }
};'''
parts = [
    '--' + boundary,
    'Content-Disposition: form-data; name="metadata"',
    'Content-Type: application/json',
    '',
    json.dumps(metadata,separators=(',',':')),
    '--' + boundary,
    'Content-Disposition: form-data; name="worker.mjs"; filename="worker.mjs"',
    'Content-Type: application/javascript+module',
    '',
    worker,
    '--' + boundary + '--',
]
body = ('\r\n'.join(parts) + '\r\n').encode('utf-8')
out = Path(r'C:\Workspace\super-creator-os\evidence\social-automation\phase5\brightbean-worker.multipart')
out.write_bytes(body)
print('bytes=', len(body))
print('sha256=', hashlib.sha256(body).hexdigest())
print('content_type=', 'multipart/form-data; boundary=' + boundary)