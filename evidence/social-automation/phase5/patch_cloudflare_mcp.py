from pathlib import Path
p = Path(r"C:\Users\chara\AppData\Local\hermes\profiles\haios-primary-operator\config.yaml")
backup = p.with_name(p.name + ".bak-brightbean-cloudflare-minimal-20260928")
backup.write_bytes(p.read_bytes())
s = p.read_text(encoding="utf-8")
start = s.index("  cloudflare:\n")
end = s.index("  context7:\n", start)
block = """  cloudflare:
    auth: oauth
    enabled: true
    tools:
      include:
        - search
        - execute
    url: https://mcp.cloudflare.com/mcp?codemode=false
"""
p.write_text(s[:start] + block + s[end:], encoding="utf-8")
print("backup=", backup)
print("cloudflare_block_updated=true")
