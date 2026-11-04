param(
  [string]$TargetName,
  [string]$TargetMac,
  [string]$CdcPort,
  [int]$StageSeconds = 20,
  [int]$SoakSeconds = 600,
  [switch]$PhoneRelay
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
if ($StageSeconds -lt 5 -or $StageSeconds -gt 120) { throw 'StageSeconds must be 5..120' }
if ($SoakSeconds -lt 10 -or $SoakSeconds -gt 1800) { throw 'SoakSeconds must be 10..1800' }
if (!(Get-Command picotool -ErrorAction SilentlyContinue)) { throw 'picotool must be in PATH' }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) {
  & py -3 -m venv (Join-Path $Root '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3 venv creation failed' }
  & $Python -m pip install -r (Join-Path $Root 'live-requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
$PortFile = Join-Path $Root 'flashed-port.txt'
$FlashArgs = @((Join-Path $Root 'flash_candidate.py'), '--root', $Root, '--port-file', $PortFile)
if ($CdcPort) { $FlashArgs += @('--cdc', $CdcPort) }
& $Python @FlashArgs
if ($LASTEXITCODE -ne 0) { throw 'Firmware update failed. See flash-log.json; live tests were not started.' }
$CdcPort = (Get-Content -Raw $PortFile).Trim()
if (!$CdcPort) { throw 'Firmware update did not identify a returning CDC port' }
$RunArgs = @((Join-Path $Root 'live_test.py'), '--output', $Root, '--duration', $StageSeconds, '--soak-seconds', $SoakSeconds)
if ($TargetName) { $RunArgs += @('--target-name', $TargetName) }
if ($TargetMac) { $RunArgs += @('--target-mac', $TargetMac) }
if ($PhoneRelay) { $RunArgs += '--phone-relay' }
if ($CdcPort) { $RunArgs += @('--cdc', $CdcPort) }
& $Python @RunArgs
$Code = $LASTEXITCODE
if ($Code -ne 0) { Write-Host 'A check or collection failed. Return the results ZIP; see summary.json.' }
else { Write-Host 'Automatic checks finished. Return the results ZIP, including SKIP/UNVERIFIED coverage.' }
exit $Code
