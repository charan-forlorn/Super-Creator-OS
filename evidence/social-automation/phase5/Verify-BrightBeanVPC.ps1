param(
    [int]$Count = 12,
    [string]$WorkerUrl = "https://brightbean-social-edge-20260928.charan254311.workers.dev",
    [string]$EvidenceDir = "$PSScriptRoot"
)

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $EvidenceDir "VPC_VERIFY_$timestamp.md"
$origin = & curl.exe -sS -o NUL -w "%{http_code}" -H "Host: 127.0.0.1" -H "X-Forwarded-Proto: https" "http://127.0.0.1:18100/health/"
$edge = & docker exec brightbean-edge sh -lc 'wget -qO- http://app:8000/health/ 2>/dev/null || curl -fsS http://app:8000/health/ 2>/dev/null || true'
$containers = & docker ps --format "{{.Names}} {{.Status}}" | Select-String "brightbean-phase3-(app|worker|postgres)|haios-woodpecker-cloudflared|brightbean-edge"

$rows = @()
for ($i = 1; $i -le $Count; $i++) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $status = & curl.exe -sS -o NUL -w "%{http_code}" --max-time 8 "$WorkerUrl/health/"
    $sw.Stop()
    $rows += [pscustomobject]@{ n = $i; http = $status; ms = $sw.ElapsedMilliseconds }
    Start-Sleep -Milliseconds 300
}

$ok = @($rows | Where-Object http -eq "200").Count
$failed = @($rows | Where-Object http -ne "200").Count

@"
# BrightBean VPC Verification — $timestamp

Origin health: $origin
Private edge response: $edge
Worker requests: $Count
HTTP 200: $ok
Non-200: $failed

## Sample
$($rows | Format-Table -AutoSize | Out-String)

## Containers
$($containers | Out-String)

## Cloudflared connector summary
$((& docker logs --tail 80 haios-woodpecker-cloudflared 2>&1 | Select-String -Pattern "(?i)Registered tunnel connection|protocol=quic|ERR|WARN" | Select-Object -Last 40 | Out-String))

## Verdict
Public stability is PASS only when the requested sample contains no unexpected non-200 responses and the local origin/private edge checks are healthy. This script never mutates Cloudflare or Docker configuration.
"@ | Set-Content -Encoding UTF8 $outFile

Write-Output "EVIDENCE=$outFile"
Write-Output "ORIGIN=$origin"
Write-Output "EDGE=$edge"
Write-Output "HTTP_200=$ok"
Write-Output "HTTP_NON200=$failed"

