$ErrorActionPreference="Stop"
$timestamp=Get-Date -Format "yyyyMMdd_HHmmss"
$outFile=Join-Path $PSScriptRoot "..\phase20\TARGETED_ACCEPTANCE_$timestamp.txt"
$cmd="docker exec brightbean-phase3-app-1 pytest -q tests/providers/test_facebook.py tests/providers/test_instagram.py tests/providers/test_tiktok.py apps/publisher/tests.py apps/publisher/test_connection_budget.py apps/publisher/test_failure_notification.py apps/publisher/test_first_comment.py apps/publisher/test_media_handling.py apps/publisher/test_publish_confirmation.py apps/social_accounts/tests/test_webhook_subscription.py apps/mcp/tests"
$lines = & pwsh -NoProfile -Command $cmd 2>&1
$exit = $LASTEXITCODE
$lines | Tee-Object -FilePath $outFile
"EXIT_CODE=$exit" | Tee-Object -FilePath $outFile -Append
"OUTPUT=$outFile"
exit $exit

