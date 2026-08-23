# SPDX-License-Identifier: GPL-3.0-only

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $SourceRef,

    [Parameter(Mandatory = $true)]
    [string] $DestinationRef,

    [Parameter(Mandatory = $true)]
    [string] $DestinationRepository,

    [string] $SourceRepository = (Split-Path -Parent $PSScriptRoot),

    [switch] $DryRun,

    [switch] $Publish
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedRepository = "github.com/wwalsh/scrcpy-launcher"
$ProjectRoot = (Resolve-Path $SourceRepository).Path
$TemporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("scrcpy-public-" + [guid]::NewGuid())

function Invoke-Git {
    param([string[]] $Arguments, [string] $WorkingDirectory)
    $output = & git -C $WorkingDirectory @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed in $WorkingDirectory`n$($output -join "`n")"
    }
    return @($output)
}

function Get-GitText {
    param([string[]] $Arguments, [string] $WorkingDirectory)
    return ((Invoke-Git -Arguments $Arguments -WorkingDirectory $WorkingDirectory) -join "`n").Trim()
}

function Get-GitLines {
    param([string[]] $Arguments, [string] $WorkingDirectory)
    return @(Invoke-Git -Arguments $Arguments -WorkingDirectory $WorkingDirectory |
        ForEach-Object { $_.ToString() } |
        Where-Object { $_ })
}

function Normalize-RepositoryUrl {
    param([string] $Url)
    $normalized = $Url.Trim().ToLowerInvariant()
    $normalized = $normalized -replace '^https?://', ''
    $normalized = $normalized -replace '^git@', ''
    $normalized = $normalized -replace ':', '/'
    return $normalized.TrimEnd('/') -replace '\.git$', ''
}

function Test-SourcePath {
    param([string] $RelativePath)
    return $RelativePath -notmatch '(^|/)(\.git|\.venv|venv|build|dist|\.cache|__pycache__)(/|$)' -and
        $RelativePath -notmatch '(^|/)(config\.json(?:\.bak)?|.*\.(log|report))$'
}

if ($DryRun -and $Publish) { throw "Choose -DryRun or -Publish, not both." }
if (-not $DryRun -and -not $Publish) {
    throw "No remote operation selected. Use -DryRun to preview or -Publish to push after validation."
}
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot ".git"))) {
    throw "SourceRepository is not a Git worktree: $ProjectRoot"
}
if ((Normalize-RepositoryUrl $DestinationRepository) -ne $ExpectedRepository) {
    throw "Refusing unrelated destination repository. Expected $ExpectedRepository."
}
if ($SourceRef -eq "master" -or $SourceRef -eq "refs/heads/master") {
    throw "Refusing to publish local master. Use an explicitly prepared public snapshot ref."
}

try {
    $sourceCommit = Get-GitText @("rev-parse", "--verify", "$SourceRef`^{commit}") $ProjectRoot
    $sourceStatus = @(Invoke-Git @("status", "--porcelain=v1", "--untracked-files=all") $ProjectRoot)
    if ($sourceStatus.Count -gt 0) { throw "Source worktree is not clean; refusing to publish." }

    $sourceFiles = @(Get-GitLines @("ls-tree", "-r", "--name-only", $SourceRef) $ProjectRoot |
        Where-Object { $_ -and (Test-SourcePath $_) })
    $allSourceFiles = @(Get-GitLines @("ls-tree", "-r", "--name-only", $SourceRef) $ProjectRoot |
        Where-Object { $_ })
    if ($sourceFiles.Count -ne $allSourceFiles.Count) {
        throw "Source ref contains a personal, generated, or otherwise forbidden path."
    }

    $versionPath = "src/version.py"
    $versionText = Get-GitText @("show", "$SourceRef`:$versionPath") $ProjectRoot
    $versionMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*["'']([^"'']+)["'']')
    if (-not $versionMatch.Success) { throw "Could not read APP_VERSION from $SourceRef." }
    $version = $versionMatch.Groups[1].Value
    $tagName = $null
    if ($SourceRef -match '^refs/tags/(v?\d+\.\d+\.\d+)$') { $tagName = $Matches[1] }
    elseif ($SourceRef -match '^v\d+\.\d+\.\d+$') { $tagName = $SourceRef }
    if ($tagName -and $tagName -ne "v$version") {
        throw "Release tag $tagName does not match APP_VERSION $version."
    }

    $remoteTags = @(Invoke-Git @("ls-remote", "--tags", $DestinationRepository, "refs/tags/v$version^{}") $ProjectRoot)
    if ($tagName -and $remoteTags.Count -gt 0) {
        $remoteTagCommit = ($remoteTags[0] -split "\s+")[0]
        if ($remoteTagCommit -ne $sourceCommit) {
            throw "Refusing to alter existing release tag $tagName."
        }
    }

    $destinationRefs = @(Invoke-Git @("ls-remote", "--heads", "--tags", $DestinationRepository, $DestinationRef) $ProjectRoot)
    if ($destinationRefs.Count -eq 0) { throw "Destination ref does not exist: $DestinationRef" }
    $destinationCommit = ($destinationRefs[0] -split "\s+")[0]

    New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
    $sourceArchive = Join-Path $TemporaryRoot "source.zip"
    $sourceTree = Join-Path $TemporaryRoot "source"
    $destinationTree = Join-Path $TemporaryRoot "destination"
    New-Item -ItemType Directory -Path $sourceTree | Out-Null
    Invoke-Git @("archive", "--format=zip", "--output=$sourceArchive", $SourceRef) $ProjectRoot | Out-Null
    Expand-Archive -LiteralPath $sourceArchive -DestinationPath $sourceTree
    Invoke-Git @("clone", "--quiet", $DestinationRepository, $destinationTree) $ProjectRoot | Out-Null
    Invoke-Git @("checkout", "--quiet", "--detach", $DestinationRef) $destinationTree | Out-Null
    Invoke-Git @("config", "user.name", "scrcpy-launcher publisher") $destinationTree | Out-Null
    Invoke-Git @("config", "user.email", "scrcpy-launcher-publisher@users.noreply.github.com") $destinationTree | Out-Null
    Invoke-Git @("clean", "-fdx") $destinationTree | Out-Null

    $destinationFiles = @(Get-GitLines @("ls-files") $destinationTree | Where-Object { $_ })
    foreach ($relative in $destinationFiles) {
        if ($sourceFiles -notcontains $relative) { Invoke-Git @("rm", "-f", "--", $relative) $destinationTree | Out-Null }
    }
    Copy-Item -Path (Join-Path $sourceTree "*") -Destination $destinationTree -Recurse -Force
    $diff = @(Invoke-Git @("status", "--short") $destinationTree)
    $plannedMessage = "Sync $SourceRef ($sourceCommit, version $version) onto $DestinationRef ($destinationCommit)."
    Write-Output $plannedMessage
    Write-Output "Tracked source files: $($sourceFiles.Count); changed destination paths: $($diff.Count)."
    Write-Output "Exact push operation: git push $DestinationRepository HEAD:$DestinationRef"
    if ($DryRun) {
        Write-Output "DRY-RUN: no commit or remote mutation performed."
        exit 0
    }

    if ($diff.Count -eq 0) { Write-Output "No changes to publish."; exit 0 }
    Invoke-Git @("add", "--all") $destinationTree | Out-Null
    Invoke-Git @("commit", "-m", "Synchronize public snapshot $version") $destinationTree | Out-Null
    $newCommit = Get-GitText @("rev-parse", "HEAD") $destinationTree
    Write-Output "Exact commit: $newCommit"
    Write-Output "Exact push operation: git push $DestinationRepository HEAD:$DestinationRef"
    Invoke-Git @("push", $DestinationRepository, "HEAD:$DestinationRef") $destinationTree | Out-Null
    Write-Output "Published $newCommit to $DestinationRef."
}
finally {
    if (Test-Path -LiteralPath $TemporaryRoot) { Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force }
}


