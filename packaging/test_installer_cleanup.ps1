# SPDX-License-Identifier: GPL-3.0-only

param([string]$NsisCompiler)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$cacheRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot ".cache\nsis-cleanup-test"))
$requiredPrefix = $projectRoot.TrimEnd('\') + '\.cache\'
if (-not $cacheRoot.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use an installer test path outside the project cache: $cacheRoot"
}

if (-not $NsisCompiler) {
    $NsisCompiler = Join-Path $env:USERPROFILE "PortableApps\NSISPortable\App\NSIS\Bin\makensis.exe"
}
$NsisCompiler = [System.IO.Path]::GetFullPath($NsisCompiler)
if (-not (Test-Path -LiteralPath $NsisCompiler -PathType Leaf)) {
    throw "NSIS compiler was not found: $NsisCompiler"
}

if (Test-Path -LiteralPath $cacheRoot) {
    Remove-Item -LiteralPath $cacheRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $cacheRoot | Out-Null

try {
    $ownedRoot = Join-Path $cacheRoot "owned"
    $outsideRoot = Join-Path $cacheRoot "outside-sentinel"
    $junctionPath = Join-Path $ownedRoot "nested\outside-link"
    $testExe = Join-Path $cacheRoot "safe-delete-test.exe"
    New-Item -ItemType Directory -Path (Join-Path $ownedRoot "nested") | Out-Null
    New-Item -ItemType Directory -Path $outsideRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $ownedRoot "owned.txt") -Value "owned"
    Set-Content -LiteralPath (Join-Path $outsideRoot "sentinel.txt") -Value "must survive"
    New-Item -ItemType Junction -Path $junctionPath -Target $outsideRoot | Out-Null

    & $NsisCompiler "/V2" "/DTestRoot=$ownedRoot" "/DOutputFile=$testExe" `
        (Join-Path $PSScriptRoot "nsis-safe-delete-test.nsi")
    if ($LASTEXITCODE -ne 0) {
        throw "NSIS cleanup harness compilation failed with exit code $LASTEXITCODE"
    }
    $testProcess = Start-Process -FilePath $testExe -Wait -PassThru -WindowStyle Hidden
    if ($testProcess.ExitCode -ne 0) {
        throw "NSIS cleanup harness failed with exit code $($testProcess.ExitCode)"
    }
    if (Test-Path -LiteralPath $ownedRoot) {
        throw "Safe cleanup did not remove the owned test tree"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $outsideRoot "sentinel.txt") -PathType Leaf)) {
        throw "Safe cleanup followed a junction and removed outside data"
    }
    Write-Host "NSIS cleanup junction test passed."
}
finally {
    if (Test-Path -LiteralPath $cacheRoot) {
        Remove-Item -LiteralPath $cacheRoot -Recurse -Force
    }
}
