$cred = Get-Content -Raw 'C:\Users\chara\AppData\Local\hermes\profiles\haios-primary-operator\mcp-tokens\cloudflare.json' | ConvertFrom-Json
$headers = @{ Authorization = "Bearer $($cred.access_token)"; 'Content-Type' = 'application/json'; Accept = 'application/json, text/event-stream' }
$body = @{ jsonrpc='2.0'; id=2; method='tools/list'; params=@{} } | ConvertTo-Json -Depth 10
$r = Invoke-WebRequest -Uri 'https://mcp.cloudflare.com/mcp' -Method POST -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 30
Write-Output $r.Content