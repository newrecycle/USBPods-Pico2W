# Execute the real Windows launcher with Python entry-point fixtures. No USB I/O.
$ErrorActionPreference = 'Stop'
$Repo = Split-Path $PSScriptRoot
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ('USBPods launcher ' + [guid]::NewGuid())
New-Item -ItemType Directory $TempRoot | Out-Null
$PreviousPath = $env:PATH
try {
  Copy-Item (Join-Path $Repo 'tools\Run-Test.ps1') $TempRoot
  & python -m venv (Join-Path $TempRoot '.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Fixture venv failed' }
  # The helper's actual behavior is covered by test_flash_candidate.py.
  @'
import json, pathlib, sys
root=pathlib.Path(__file__).parent
args=sys.argv[1:]
(root/'flash-args.json').write_text(json.dumps(args))
if (root/'fail-flash').exists():sys.exit(7)
pathlib.Path(args[args.index('--port-file')+1]).write_text('COM7')
'@ | Set-Content (Join-Path $TempRoot 'flash_candidate.py')
  @'
import json, pathlib, sys
root=pathlib.Path(__file__).parent
(root/'run-args.json').write_text(json.dumps(sys.argv[1:]))
sys.exit(9 if (root/'fail-run').exists() else 0)
'@ | Set-Content (Join-Path $TempRoot 'live_test.py')
  '@echo off' | Set-Content (Join-Path $TempRoot 'picotool.cmd')
  $env:PATH = $TempRoot + ';' + $PreviousPath
  $Shell = (Get-Process -Id $PID).Path
  $Launcher = Join-Path $TempRoot 'Run-Test.ps1'
  function Run-Launcher([int]$Expected) {
    & $Shell -NoProfile -ExecutionPolicy Bypass -File $Launcher -CdcPort COM3 -TargetName "Justin's AirPods Pro" -StageSeconds 20 -SoakSeconds 600 -SessionOnly *> (Join-Path $TempRoot 'launcher.log')
    if ($LASTEXITCODE -ne $Expected) { throw "Launcher exited $LASTEXITCODE; expected $Expected. $(Get-Content -Raw (Join-Path $TempRoot 'launcher.log'))" }
  }
  Run-Launcher 0
  $FlashArgs = Get-Content -Raw (Join-Path $TempRoot 'flash-args.json') | ConvertFrom-Json
  $RunArgs = Get-Content -Raw (Join-Path $TempRoot 'run-args.json') | ConvertFrom-Json
  if ($FlashArgs[[Array]::IndexOf($FlashArgs, '--cdc') + 1] -ne 'COM3') { throw 'Original port was not sent to flasher' }
  if ($RunArgs[[Array]::IndexOf($RunArgs, '--cdc') + 1] -ne 'COM7') { throw 'Returning port was not sent to tests' }
  if ($RunArgs[[Array]::IndexOf($RunArgs, '--target-name') + 1] -ne "Justin's AirPods Pro") { throw 'Target argument was split' }
  if ($RunArgs -notcontains '--session-only') { throw 'Session-only mode was not forwarded' }
  New-Item (Join-Path $TempRoot 'fail-run') | Out-Null
  Run-Launcher 9
  Remove-Item (Join-Path $TempRoot 'run-args.json')
  New-Item (Join-Path $TempRoot 'fail-flash') | Out-Null
  Run-Launcher 1
  if (Test-Path (Join-Path $TempRoot 'run-args.json')) { throw 'Tests ran after flash failure' }
  Write-Host 'PASS Windows launcher: automatic flash, changed COM, quoted paths/target, test failure exit, flash failure stop'
} finally {
  $env:PATH = $PreviousPath
  Remove-Item -Recurse -Force $TempRoot
}
# The last exercised child deliberately exits 1. GitHub's pwsh wrapper checks
# LASTEXITCODE after this script returns, so finish with this test's result.
exit 0
