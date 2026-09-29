import subprocess, pathlib, json, sys
b64 = pathlib.Path(r"C:\Workspace\super-creator-os\evidence\social-automation\phase5\worker.mjs.b64").read_text(encoding="ascii").strip()
prompt = f"""Call only mcp__cloudflare__post_accounts_workers_workers_versions.
account_id=cb98ff5a98ddb6c0f09450505be7c3f5
worker_id=d2dc373c2eb94164a376affc57cdf68d
deploy=true
Body JSON:
{json.dumps({
  "main_module":"worker.mjs",
  "compatibility_date":"2026-09-01",
  "annotations":{"workers/message":"BrightBean stable public edge via Workers VPC","workers/tag":"brightbean-vpc-edge-20260928"},
  "bindings":[{"name":"BRIGHTBEAN","type":"vpc_service","service_id":"01a0e4c6-ae62-74e0-8cbf-4df204bec536"}],
  "modules":[{"name":"worker.mjs","content_type":"application/javascript+module","content_base64":b64}]
}, separators=(",",":"))}
Return only compact JSON with version id, number, created_on, deployed, urls, and binding summary, or exact API error."""
r=subprocess.run(["hermes","-z",prompt,"--in",r"C:\Workspace\super-creator-os","--yolo"],capture_output=True,text=True)
print(r.stdout)
print(r.stderr,file=sys.stderr)
raise SystemExit(r.returncode)
