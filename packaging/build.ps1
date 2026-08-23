# SPDX-License-Identifier: GPL-3.0-only

param(
    [switch]$SkipInstaller,
    [string]$NsisCompiler,
    [string]$DependencyCache,
    [switch]$OfflineDependencies,
    [switch]$SkipBundledTools
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$resolvedDependencyCache = if ($DependencyCache) {
    [System.IO.Path]::GetFullPath($DependencyCache)
} else {
    Join-Path $projectRoot ".cache\dependencies"
}

if ($SkipBundledTools -and -not $SkipInstaller) {
    throw "-SkipBundledTools creates a developer-only package and must be combined with -SkipInstaller."
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Remove-KnownBuildDirectory {
    param([string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $requiredPrefix = $projectRoot.TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove build path outside the project: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}

function Resolve-NsisCompiler {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        $resolvedExplicitPath = [System.IO.Path]::GetFullPath($ExplicitPath)
        if (-not (Test-Path -LiteralPath $resolvedExplicitPath -PathType Leaf)) {
            throw "NSIS compiler was not found at the explicit path: $resolvedExplicitPath"
        }
        return $resolvedExplicitPath
    }

    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($env:NSIS_HOME) {
        $candidates.Add((Join-Path $env:NSIS_HOME "Bin\makensis.exe"))
        $candidates.Add((Join-Path $env:NSIS_HOME "makensis.exe"))
    }

    $pathCommand = Get-Command "makensis.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($pathCommand) {
        $candidates.Add($pathCommand.Source)
    }

    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE "PortableApps\NSISPortable\App\NSIS\Bin\makensis.exe"))
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates.Add((Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe"))
    }
    if ($env:ProgramFiles) {
        $candidates.Add((Join-Path $env:ProgramFiles "NSIS\makensis.exe"))
    }

    $resolvedCandidate = $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
    if (-not $resolvedCandidate) {
        throw "NSIS 3 was not found. Install it, set NSIS_HOME, pass -NsisCompiler, or rerun with -SkipInstaller."
    }
    return [System.IO.Path]::GetFullPath($resolvedCandidate)
}

Push-Location $projectRoot
try {
    $versionText = Get-Content -LiteralPath "src\version.py" -Raw
    $versionMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*"([0-9]+(?:\.[0-9]+){2,3})"')
    if (-not $versionMatch.Success) {
        throw "Could not read APP_VERSION from src\version.py"
    }
    $appVersion = $versionMatch.Groups[1].Value
    $versionParts = @($appVersion.Split("."))
    while ($versionParts.Count -lt 4) {
        $versionParts += "0"
    }
    $appVersionQuad = $versionParts -join "."

    Invoke-Checked { & $pythonCommand "packaging\security_audit.py" } "Dependency security policy"
    Invoke-Checked { & $pythonCommand -m unittest discover -s tests -q } "Tests"
    Remove-KnownBuildDirectory (Join-Path $projectRoot "build")
    Remove-KnownBuildDirectory (Join-Path $projectRoot "dist")

    Invoke-Checked {
        & $pythonCommand "packaging\generate_version_info.py" $appVersion "build\version_info.txt"
    } "Version resource generation"
    Invoke-Checked {
        & $pythonCommand -m PyInstaller --noconfirm "packaging\scrcpy-launcher.spec"
    } "PyInstaller"

    $packageDirectory = Join-Path $projectRoot "dist\scrcpy-launcher"
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packageDirectory
    Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD-PARTY-NOTICES.md") -Destination $packageDirectory
    Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination $packageDirectory -Recurse

    $artifactDirectory = Join-Path $projectRoot "dist\artifacts"
    New-Item -ItemType Directory -Path $artifactDirectory -Force | Out-Null
    if (-not $SkipBundledTools) {
        $stageArguments = @(
            "packaging\stage_scrcpy.py",
            "--manifest", "packaging\dependencies\scrcpy-win64-v4.1.json",
            "--cache-dir", $resolvedDependencyCache,
            "--destination", (Join-Path $packageDirectory "tools\scrcpy"),
            "--source-artifacts-dir", (Join-Path $artifactDirectory "sources"),
            "--licenses-dir", (Join-Path $packageDirectory "licenses")
        )
        if ($OfflineDependencies) {
            $stageArguments += "--offline"
        }
        Invoke-Checked { & $pythonCommand @stageArguments } "scrcpy dependency staging"
    }

    $smokeArguments = @("--package-smoke-test")
    if ($SkipBundledTools) {
        $smokeArguments += "--allow-missing-bundled-tools"
    }
    Invoke-Checked {
        & "dist\scrcpy-launcher\scrcpy-launcher.exe" @smokeArguments
    } "Packaged application smoke test"

    $artifactSuffix = if ($SkipBundledTools) { "-unbundled" } else { "" }
    $portableArchive = Join-Path $artifactDirectory "scrcpy-launcher-$appVersion$artifactSuffix-portable.zip"
    $portableStageParent = Join-Path $projectRoot "dist\portable-stage"
    New-Item -ItemType Directory -Path $portableStageParent -Force | Out-Null
    Copy-Item -LiteralPath $packageDirectory -Destination $portableStageParent -Recurse
    $portablePackageDirectory = Join-Path $portableStageParent "scrcpy-launcher"
    Set-Content -LiteralPath (Join-Path $portablePackageDirectory "portable.marker") -Value "portable" -Encoding ascii
    Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\default-config.json") -Destination (Join-Path $portablePackageDirectory "default-config.json")
    Compress-Archive -LiteralPath $portablePackageDirectory -DestinationPath $portableArchive

    if (-not $SkipInstaller) {
        $nsisPath = Resolve-NsisCompiler $NsisCompiler
        $installerPath = Join-Path $artifactDirectory "scrcpy-launcher-$appVersion-setup.exe"
        Invoke-Checked {
            & $nsisPath "/V3" "/DAppVersion=$appVersion" "/DAppVersionQuad=$appVersionQuad" "/DSourceDir=$packageDirectory" "/DOutputDir=$artifactDirectory" "packaging\scrcpy-launcher.nsi"
        } "NSIS"
    }

    $verificationArguments = @(
        "packaging\verify_release.py",
        "--package-dir", $packageDirectory,
        "--portable-archive", $portableArchive
    )
    if (-not $SkipInstaller) {
        $verificationArguments += @("--installer", $installerPath)
    }
    if ($SkipBundledTools) {
        $verificationArguments += "--allow-missing-bundled-tools"
    }
    Invoke-Checked { & $pythonCommand @verificationArguments } "release lifecycle verification"

    Get-ChildItem -LiteralPath $artifactDirectory -File -Recurse |
        Where-Object { $_.Extension -in ".zip", ".exe", ".xz", ".gz" } |
        ForEach-Object {
            $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            Set-Content -LiteralPath ($_.FullName + ".sha256") -Value "$hash  $($_.Name)" -Encoding ascii
        }

    Write-Host "Build completed for scrcpy-launcher $appVersion"
    Get-ChildItem -LiteralPath $artifactDirectory -File | Select-Object Name, Length
}
finally {
    Pop-Location
}
