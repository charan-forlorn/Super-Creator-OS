param(
  [Parameter(Mandatory=$true)][string]$AccountId,
  [Parameter(Mandatory=$true)][string]$TunnelId,
  [Parameter(Mandatory=$true)][string]$Hostname,
  [Parameter(Mandatory=$true)][string]$ZoneId,
  [string]$ApiToken = $env:CLOUDFLARE_API_TOKEN,
  [switch]$NoDns
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($ApiToken)){ throw "CLOUDFLARE_API_TOKEN is required; it is never written to disk or printed." }
$headers=@{Authorization="Bearer $ApiToken";"Content-Type"="application/json"}
$accountBase="https://api.cloudflare.com/client/v4/accounts/$AccountId"
$zoneBase="https://api.cloudflare.com/client/v4/zones/$ZoneId"
$configUrl="$accountBase/cfd_tunnel/$TunnelId/configurations"
$cfg=(Invoke-RestMethod -Uri $configUrl -Headers $headers -Method Get).result.config
$ingress=@($cfg.ingress)
if(-not $ingress){$ingress=@()}
$catch=$null
if($ingress.Count -gt 0 -and -not $ingress[-1].hostname -and $ingress[-1].service){$catch=$ingress[-1];$ingress=$ingress[0..($ingress.Count-2)]}
$found=$false
for($i=0;$i -lt $ingress.Count;$i++){
  if($ingress[$i].hostname -eq $Hostname){
    $ingress[$i]=[ordered]@{hostname=$Hostname;service="http://brightbean-edge:80";originRequest=@{}}
    $found=$true
  }
}
if(-not $found){$ingress += [ordered]@{hostname=$Hostname;service="http://brightbean-edge:80";originRequest=@{}}}
if($catch){$ingress += $catch}else{$ingress += [ordered]@{service="http_status:404"}}
$payload=@{config=@{ingress=$ingress}} | ConvertTo-Json -Depth 12
Invoke-RestMethod -Uri $configUrl -Headers $headers -Method Put -Body $payload | Out-Null
if(-not $NoDns){
  $dnsUrl="$zoneBase/dns_records?type=CNAME&name=$([uri]::EscapeDataString($Hostname))"
  $existing=(Invoke-RestMethod -Uri $dnsUrl -Headers $headers -Method Get).result
  $target="$TunnelId.cfargotunnel.com"
  if($existing.Count -eq 0){
    $body=@{type="CNAME";name=$Hostname;content=$target;proxied=$true;ttl=1}|ConvertTo-Json
    Invoke-RestMethod -Uri "$zoneBase/dns_records" -Headers $headers -Method Post -Body $body | Out-Null
  } else {
    foreach($r in $existing){
      if($r.content -ne $target -or -not $r.proxied){
        $body=@{type="CNAME";name=$Hostname;content=$target;proxied=$true;ttl=1}|ConvertTo-Json
        Invoke-RestMethod -Uri "$zoneBase/dns_records/$($r.id)" -Headers $headers -Method Put -Body $body | Out-Null
      }
    }
  }
}
Write-Output "Cloudflare route configured: $Hostname -> http://brightbean-edge:80"
Write-Output "DNS target: $TunnelId.cfargotunnel.com"
