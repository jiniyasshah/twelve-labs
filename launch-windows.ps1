$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Missing private venv. Run INSTALL_WINDOWS.bat first.' }

# Guard direct launches as well as RUN_WINDOWS.bat.
& $python -X utf8 verify_install.py
if ($LASTEXITCODE -ne 0) { throw 'Kitten Studio dependencies are incomplete. Run REPAIR_WINDOWS.bat.' }

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '120'
$env:HF_HUB_ETAG_TIMEOUT = '60'
$env:HF_XET_NUM_CONCURRENT_RANGE_GETS = '2'
if ($env:KITTEN_STUDIO_OFFLINE -eq '1') { $env:HF_HUB_OFFLINE = '1' }
else { $env:HF_HUB_OFFLINE = '0' }

# Credentials: use the standard HF_TOKEN environment variable. The Python server
# also reads an optional local .env (without overriding a real environment variable).
# No encrypted-token vault or token reset utility is used in this release.
if ($env:HF_TOKEN -and $env:HF_TOKEN.Trim()) {
  Write-Host 'Hugging Face token: HF_TOKEN environment variable detected (not validated).'
} elseif (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.env')) {
  Write-Host 'Hugging Face token: checking optional .env inside Python (not validated).'
} else {
  Write-Host 'Hugging Face token: none in process environment (public models can still download).'
}

$port = if ($env:KITTEN_STUDIO_PORT) { $env:KITTEN_STUDIO_PORT } else { '8765' }
if ($port -notmatch '^\d{2,5}$' -or [int]$port -gt 65535) { throw 'Invalid KITTEN_STUDIO_PORT.' }
$env:KITTEN_STUDIO_PORT = $port
Write-Host ''
Write-Host '  Kitten Studio' -ForegroundColor White
Write-Host '  --------------------------------'
Write-Host "  http://127.0.0.1:$port"
Write-Host "  Model downloads: $(if($env:HF_HUB_OFFLINE -eq '1'){'OFFLINE (cache only)'}else{'ONLINE + cache'})"
Write-Host "  Python: $python"
Write-Host '  Press Ctrl+C to stop.'
Write-Host ''

# Open a browser tab only after the server is accepting requests.
$launchUrl = "http://127.0.0.1:$port"
$openWhenReady = @"
for (`$i=0; `$i -lt 60; `$i++) {
  try {
    `$response = Invoke-WebRequest -Uri '$launchUrl' -UseBasicParsing -TimeoutSec 1
    if (`$response.StatusCode -eq 200) { Start-Process -FilePath '$launchUrl'; break }
  } catch {}
  Start-Sleep -Milliseconds 800
}
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($openWhenReady))
try { Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @('-NoProfile','-EncodedCommand', $encoded) | Out-Null } catch {}
& $python -X utf8 server.py
exit $LASTEXITCODE
