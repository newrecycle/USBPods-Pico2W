#requires -Version 7.0
<#
  Non-destructive by default. Run only AFTER the verified reconciliation
  branch was accepted into the target branch and the draft PRs were resolved.
  This script cannot and does not touch firmware, raw audio, or a dirty worktree.
  Dry run: pwsh tools/Cleanup-Reconciled-Workers.ps1
  Execute: pwsh tools/Cleanup-Reconciled-Workers.ps1 -Apply
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Target = 'work/local-windows-followup-20261107'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Must run inside the USBPods git repository' }
$origin = (& git -C $repoRoot remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $origin -notmatch 'newrecycle/USBPods-Pico2W(\.git)?$') {
    throw "Origin is not the expected USBPods repository; refusing cleanup"
}
$baseline = '175ace9f09554881b554e8226544e78ce10d06a1'
$records = @(
    @{ Name='audit/capture-lifecycle-175ace9-gpt6-20261107'; Head='7a06d4ab97f16f3db318186194a8612ef100f069'; File='docs/CAPTURE-LIFECYCLE-DIAGNOSIS-175ACE9.md' },
    @{ Name='audit/mic-close-175ace9-20261107'; Head='cc27598f00112f62337e1dbd5ed8cebb06125314'; File='docs/MIC-CLOSE-DIAGNOSIS-175ACE9.md' },
    @{ Name='audit/runner-completion-175ace9'; Head='db4b82ca54bf619f570a5897ad5db535d1f2a390'; File='docs/RUNNER-COMPLETION-DIAGNOSIS-175ACE9.md' },
    @{ Name='audit/core1-service-175ace9'; Head='9e25083aa86a5e80991bfe05db35d6821edeb5e6'; File='docs/DUALCORE-192K-DIAGNOSIS-175ACE9.md' }
)
& git -C $repoRoot fetch --no-tags origin
if ($LASTEXITCODE -ne 0) { throw 'Cannot refresh origin; no cleanup attempted' }
$targetRef = 'refs/remotes/origin/' + $Target
$targetSha = (& git -C $repoRoot rev-parse $targetRef).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Target tracking ref missing' }
& git -C $repoRoot merge-base --is-ancestor $baseline $targetSha
if ($LASTEXITCODE -ne 0) { throw 'Target is not a descendant of pinned source' }
$reportRef = $targetRef + ':docs/SEQUENTIAL-VALIDATION-REPORT-20261107.md'
& git -C $repoRoot cat-file -e $reportRef
if ($LASTEXITCODE -ne 0) { throw 'Final audit report not present in target; do not delete worker evidence' }

# Preflight EVERY source before modifying any ref. No source may have changed.
foreach ($record in $records) {
    $ref = 'refs/remotes/origin/' + $record.Name
    $head = (& git -C $repoRoot rev-parse $ref).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -ne $record.Head) {
        throw "Worker branch moved or is missing: $($record.Name)"
    }
    $changed = @(& git -C $repoRoot diff --name-only $baseline $head)
    if ($LASTEXITCODE -ne 0 -or $changed.Count -ne 1 -or $changed[0] -ne $record.File) {
        throw "Worker branch has changes besides its sole reviewed Markdown: $($record.Name)"
    }
    $workerFile = $ref + ':' + $record.File
    $targetFile = $targetRef + ':' + $record.File
    $workerBlob = (& git -C $repoRoot rev-parse $workerFile).Trim()
    $targetBlob = (& git -C $repoRoot rev-parse $targetFile).Trim()
    if ($LASTEXITCODE -ne 0 -or $workerBlob -ne $targetBlob) {
        throw "Worker report blob was not preserved verbatim: $($record.Name)"
    }
}

# The reconciliation branch itself may be retired only if fully
# accepted into Target. This makes it safe to keep just main + development.
$cleanupRecords = @($records)
$auditName = 'audit/sequential-validation-20261107-gpt6'
$auditRef = 'refs/remotes/origin/' + $auditName
& git -C $repoRoot show-ref --verify --quiet $auditRef
if ($LASTEXITCODE -eq 0) {
    $auditHead = (& git -C $repoRoot rev-parse $auditRef).Trim()
    & git -C $repoRoot merge-base --is-ancestor $auditHead $targetSha
    if ($LASTEXITCODE -ne 0) {
        throw 'The independent reconciliation branch is not integrated; do not clean it'
    }
    $cleanupRecords += @{ Name=$auditName; Head=$auditHead; File='' }
}

# Check out-of-band local state: do not erase a checked-out dirty worker.
$worktreeText = (& git -C $repoRoot worktree list --porcelain) -join [Environment]::NewLine
$worktrees = @()
foreach ($block in ($worktreeText -split '(\r?\n){2,}')) {
    $pathLine = @($block -split '\r?\n' | Where-Object { $_ -match '^worktree ' })
    $branchLine = @($block -split '\r?\n' | Where-Object { $_ -match '^branch refs/heads/' })
    if (!$pathLine.Count -or !$branchLine.Count) { continue }
    $folder = $pathLine[0].Substring(9)
    $localBranch = $branchLine[0].Substring(18)
    if (@($cleanupRecords | Where-Object { $_.Name -eq $localBranch }).Count) {
        $dirty = @(& git -C $folder status --porcelain)
        if ($LASTEXITCODE -ne 0 -or $dirty.Count) {
            throw "Worker worktree is dirty or inaccessible; no cleanup: $folder"
        }
        $worktrees += @{Path=$folder; Branch=$localBranch}
    }
}

Write-Host "Verified target $Target @ $targetSha"
Write-Host 'The four unchanged worker documents are present. PR #5/#6 should already be closed/reconciled.'
foreach ($wt in $worktrees) { Write-Host "Clean worker worktree: $($wt.Path) [$($wt.Branch)]" }
foreach ($record in $cleanupRecords) { Write-Host "Eligible remote branch: $($record.Name) @ $($record.Head)" }

if (!$Apply) {
    Write-Host 'DRY RUN ONLY. Pass -Apply after PR review and approved integration.'
    exit 0
}

foreach ($wt in $worktrees) {
    & git -C $repoRoot worktree remove $wt.Path
    if ($LASTEXITCODE -ne 0) { throw "Failed to remove worktree: $($wt.Path)" }
}
foreach ($record in $cleanupRecords) {
    & git -C $repoRoot push origin --delete $record.Name
    if ($LASTEXITCODE -ne 0) { throw "Failed remote deletion: $($record.Name)" }
    $local = (& git -C $repoRoot rev-parse --verify ('refs/heads/' + $record.Name) 2>$null)
    if ($LASTEXITCODE -eq 0 -and $local.Trim() -eq $record.Head) {
        & git -C $repoRoot branch -D $record.Name
        if ($LASTEXITCODE -ne 0) { throw "Failed local branch deletion: $($record.Name)" }
    }
}
& git -C $repoRoot worktree prune
if ($LASTEXITCODE -ne 0) { throw 'Git worktree metadata pruning failed' }
Write-Host 'Completed verified cleanup of reviewed worker refs, eligible audit ref and clean local worktrees.'
