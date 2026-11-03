param(
  [string]$TargetName,
  [string]$TargetMac,
  [string]$CdcPort,
  [string]$UartPort,
  [int]$StageSeconds = 20,
  [int]$SoakSeconds = 600,
  [switch]$PhoneRelay
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (!(Test-Path $Python)) {
  & py -3 -m venv (Join-Path $Root '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3 venv creation failed' }
  & $Python -m pip install -r (Join-Path $Root 'live-requirements.txt')
  if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
$RunArgs = @((Join-Path $Root 'live_test.py'), '--output', $Root, '--duration', $StageSeconds, '--soak-seconds', $SoakSeconds)
if ($TargetName) { $RunArgs += @('--target-name', $TargetName) }
if ($TargetMac) { $RunArgs += @('--target-mac', $TargetMac) }
if ($PhoneRelay) { $RunArgs += '--phone-relay' }
if ($CdcPort) { $RunArgs += @('--cdc', $CdcPort) }
if ($UartPort) { $RunArgs += @('--uart', $UartPort) }
& $Python @RunArgs
$Code = $LASTEXITCODE
if ($Code -ne 0) { Write-Host 'A check or collection failed. Return the results ZIP; see summary.json.' }
else { Write-Host 'Automatic checks finished. Return the results ZIP, including SKIP/UNVERIFIED coverage.' }
exit $Code
