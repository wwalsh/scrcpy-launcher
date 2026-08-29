# SPDX-License-Identifier: GPL-3.0-only

param(
    [string]$PackageDirectory,
    [string]$OutputDirectory,
    [string]$LauncherGenerator,
    [string]$PortableAppsInstaller,
    [string]$ArtifactDirectory,
    [switch]$BuildPackage,
    [switch]$CreateInstaller,
    [string]$DependencyCache,
    [switch]$OfflineDependencies,
    [switch]$SkipSmokeTest,
    [switch]$AllowMissingBundledTools
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonCommand = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$templateDirectory = Join-Path $projectRoot "packaging\portableapps"
$resolvedPackageDirectory = if ($PackageDirectory) {
    [System.IO.Path]::GetFullPath($PackageDirectory)
} else {
    Join-Path $projectRoot "dist\scrcpy-launcher"
}
$resolvedOutputDirectory = if ($OutputDirectory) {
    [System.IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $projectRoot "dist\portableapps-stage\scrcpy-launcherPortable"
}

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Assert-SafeOutputPath {
    param([string]$Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $requiredPrefix = (Join-Path $projectRoot "dist").TrimEnd('\') + '\'
    if (-not $fullPath.StartsWith($requiredPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "PortableApps output must remain beneath the project dist directory: $fullPath"
    }
    if ([System.IO.Path]::GetFileName($fullPath) -ne "scrcpy-launcherPortable") {
        throw "PortableApps output directory must be named scrcpy-launcherPortable: $fullPath"
    }
    return $fullPath
}

function Remove-SafeBuildDirectory {
    param([string]$Path)
    $safePath = Assert-SafeOutputPath $Path
    if (Test-Path -LiteralPath $safePath) {
        Remove-Item -LiteralPath $safePath -Recurse -Force
    }
}

function Resolve-LauncherGenerator {
    param([string]$ExplicitPath)
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($ExplicitPath) {
        $candidates.Add([System.IO.Path]::GetFullPath($ExplicitPath))
    }
    if ($env:PORTABLEAPPS_LAUNCHER_HOME) {
        $candidates.Add((Join-Path $env:PORTABLEAPPS_LAUNCHER_HOME "PortableApps.comLauncherGenerator.exe"))
    }
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE "PortableApps\PortableApps.comLauncher\PortableApps.comLauncherGenerator.exe"))
    }
    $resolved = $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
    if (-not $resolved) {
        throw "PortableApps.com Launcher Generator was not found. Pass -LauncherGenerator or set PORTABLEAPPS_LAUNCHER_HOME."
    }

    $generatorPath = [System.IO.Path]::GetFullPath($resolved)
    $generatorRoot = Split-Path -Parent $generatorPath
    $generatorAppInfo = Join-Path $generatorRoot "App\AppInfo\appinfo.ini"
    $generatorNsis = Join-Path $generatorRoot "App\NSIS\makensis.exe"
    $generatorSource = Join-Path $generatorRoot "Other\Source\PortableApps.comLauncher.nsi"
    if (-not (Test-Path -LiteralPath $generatorAppInfo -PathType Leaf)) {
        throw "PortableApps Launcher metadata is missing: $generatorAppInfo"
    }
    $versionText = Select-String -LiteralPath $generatorAppInfo -Pattern '^PackageVersion=(.+)$' |
        Select-Object -First 1
    if (-not $versionText -or [version]$versionText.Matches[0].Groups[1].Value -lt [version]'2.2.9.0') {
        throw "PortableApps.com Launcher 2.2.9 or newer is required."
    }
    foreach ($required in ($generatorNsis, $generatorSource)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "PortableApps Launcher build dependency is missing: $required"
        }
    }
    return $generatorPath
}

function Resolve-PortableAppsInstaller {
    param([string]$ExplicitPath)
    $candidates = [System.Collections.Generic.List[string]]::new()
    if ($ExplicitPath) {
        $candidates.Add([System.IO.Path]::GetFullPath($ExplicitPath))
    }
    if ($env:PORTABLEAPPS_INSTALLER_HOME) {
        $candidates.Add((Join-Path $env:PORTABLEAPPS_INSTALLER_HOME "PortableApps.comInstaller.exe"))
    }
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE "PortableApps\PortableApps.comInstaller\PortableApps.comInstaller.exe"))
    }
    $resolved = $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
    if (-not $resolved) {
        throw "PortableApps.com Installer was not found. Pass -PortableAppsInstaller or set PORTABLEAPPS_INSTALLER_HOME."
    }

    $installerPath = [System.IO.Path]::GetFullPath($resolved)
    $installerRoot = Split-Path -Parent $installerPath
    $installerAppInfo = Join-Path $installerRoot "App\AppInfo\appinfo.ini"
    $installerNsis = Join-Path $installerRoot "App\nsis\makensis.exe"
    $installerSource = Join-Path $installerRoot "Other\Source\InstallerWizard.nsi"
    if (-not (Test-Path -LiteralPath $installerAppInfo -PathType Leaf)) {
        throw "PortableApps Installer metadata is missing: $installerAppInfo"
    }
    $versionText = Select-String -LiteralPath $installerAppInfo -Pattern '^PackageVersion=(.+)$' |
        Select-Object -First 1
    if (-not $versionText -or [version]$versionText.Matches[0].Groups[1].Value -lt [version]'3.9.18.0') {
        throw "PortableApps.com Installer 3.9.18 or newer is required."
    }
    foreach ($required in ($installerNsis, $installerSource)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "PortableApps Installer build dependency is missing: $required"
        }
    }
    return $installerPath
}

function Update-StagedVersion {
    param([string]$AppInfoPath, [string]$Version)
    $parts = @($Version.Split('.'))
    while ($parts.Count -lt 4) {
        $parts += "0"
    }
    $packageVersion = $parts -join "."
    $text = [System.IO.File]::ReadAllText($AppInfoPath)
    $text = [regex]::Replace($text, '(?m)^PackageVersion=.*$', "PackageVersion=$packageVersion")
    $text = [regex]::Replace($text, '(?m)^DisplayVersion=.*$', "DisplayVersion=$Version")
    [System.IO.File]::WriteAllText(
        $AppInfoPath,
        $text,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Get-FileSnapshot {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return "missing"
    }
    $item = Get-Item -LiteralPath $Path
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    return "$hash|$($item.Length)|$($item.LastWriteTimeUtc.Ticks)"
}

function Invoke-PortableLauncherSmoke {
    param([string]$LauncherPath, [string]$Description)
    $smokeStart = @{
        FilePath = $LauncherPath
        ArgumentList = "--portableapps-smoke-test"
        Wait = $true
        PassThru = $true
        WindowStyle = "Hidden"
    }
    $smokeProcess = Start-Process @smokeStart
    if ($smokeProcess.ExitCode -ne 0) {
        throw "$Description failed with exit code $($smokeProcess.ExitCode)"
    }
}

$resolvedOutputDirectory = Assert-SafeOutputPath $resolvedOutputDirectory

Push-Location $projectRoot
try {
    if ($BuildPackage) {
        $buildArguments = @{ SkipInstaller = $true; SkipPortableApps = $true }
        if ($DependencyCache) {
            $buildArguments.DependencyCache = $DependencyCache
        }
        if ($OfflineDependencies) {
            $buildArguments.OfflineDependencies = $true
        }
        & (Join-Path $PSScriptRoot "build.ps1") @buildArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Application package build failed with exit code $LASTEXITCODE"
        }
    }

    if (-not (Test-Path -LiteralPath $resolvedPackageDirectory -PathType Container)) {
        throw "PyInstaller package directory is missing: $resolvedPackageDirectory"
    }
    if (-not (Test-Path -LiteralPath $templateDirectory -PathType Container)) {
        throw "PortableApps template directory is missing: $templateDirectory"
    }

    $resolvedGenerator = Resolve-LauncherGenerator $LauncherGenerator
    Remove-SafeBuildDirectory $resolvedOutputDirectory
    New-Item -ItemType Directory -Path $resolvedOutputDirectory -Force | Out-Null
    Get-ChildItem -LiteralPath $templateDirectory -Force |
        Copy-Item -Destination $resolvedOutputDirectory -Recurse -Force

    $payloadDirectory = Join-Path $resolvedOutputDirectory "App\scrcpy-launcher"
    New-Item -ItemType Directory -Path $payloadDirectory -Force | Out-Null
    Get-ChildItem -LiteralPath $resolvedPackageDirectory -Force |
        Copy-Item -Destination $payloadDirectory -Recurse -Force

    $versionText = Get-Content -LiteralPath "src\version.py" -Raw
    $versionMatch = [regex]::Match($versionText, 'APP_VERSION\s*=\s*"([0-9]+(?:\.[0-9]+){2,3})"')
    if (-not $versionMatch.Success) {
        throw "Could not read APP_VERSION from src\version.py"
    }
    Update-StagedVersion (
        Join-Path $resolvedOutputDirectory "App\AppInfo\appinfo.ini"
    ) $versionMatch.Groups[1].Value

    $verificationArguments = @(
        "packaging\verify_portableapps.py",
        "--package-dir", $resolvedOutputDirectory
    )
    if ($AllowMissingBundledTools) {
        $verificationArguments += "--allow-missing-bundled-tools"
    }
    Invoke-Checked {
        & $pythonCommand @verificationArguments --phase staged
    } "PortableApps staged-package verification"

    $generatorStart = @{
        FilePath = $resolvedGenerator
        ArgumentList = ('"' + $resolvedOutputDirectory + '"')
        Wait = $true
        PassThru = $true
        WindowStyle = "Hidden"
    }
    $generatorProcess = Start-Process @generatorStart
    if ($generatorProcess.ExitCode -ne 0) {
        throw "PortableApps Launcher Generator failed with exit code $($generatorProcess.ExitCode)"
    }
    Invoke-Checked {
        & $pythonCommand @verificationArguments --phase launcher
    } "PortableApps generated-launcher verification"

    if (-not $SkipSmokeTest) {
        $hostLog = if ($env:LOCALAPPDATA) {
            Join-Path $env:LOCALAPPDATA "scrcpy-launcher\portableapps-smoke.log"
        } else {
            Join-Path ([System.IO.Path]::GetTempPath()) "scrcpy-launcher-portableapps-smoke.log"
        }
        $hostLogBefore = Get-FileSnapshot $hostLog
        $portableLauncher = Join-Path $resolvedOutputDirectory "scrcpy-launcherPortable.exe"
        Invoke-PortableLauncherSmoke $portableLauncher "PortableApps launcher smoke test"
        Invoke-Checked {
            & $pythonCommand @verificationArguments --phase smoke
        } "PortableApps smoke-state verification"

        $portableConfig = Join-Path $resolvedOutputDirectory "Data\config.json"
        $configHashBefore = (Get-FileHash -LiteralPath $portableConfig -Algorithm SHA256).Hash
        Invoke-PortableLauncherSmoke $portableLauncher "PortableApps repeat-launch smoke test"
        $configHashAfter = (Get-FileHash -LiteralPath $portableConfig -Algorithm SHA256).Hash
        if ($configHashAfter -ne $configHashBefore) {
            throw "PortableApps repeat launch replaced the existing configuration"
        }
        if ((Get-FileSnapshot $hostLog) -ne $hostLogBefore) {
            throw "PortableApps smoke testing changed the host log path: $hostLog"
        }

        $spaceTestDirectory = Join-Path $projectRoot "dist\portableapps-space-test\Path With Spaces\scrcpy-launcherPortable"
        Remove-SafeBuildDirectory $spaceTestDirectory
        New-Item -ItemType Directory -Path (Split-Path -Parent $spaceTestDirectory) -Force | Out-Null
        Copy-Item -LiteralPath $resolvedOutputDirectory -Destination $spaceTestDirectory -Recurse
        Remove-Item -LiteralPath (Join-Path $spaceTestDirectory "Data") -Recurse -Force
        try {
            Invoke-PortableLauncherSmoke (
                Join-Path $spaceTestDirectory "scrcpy-launcherPortable.exe"
            ) "PortableApps path-with-spaces smoke test"
            $spaceVerification = @(
                "packaging\verify_portableapps.py",
                "--package-dir", $spaceTestDirectory,
                "--phase", "smoke"
            )
            if ($AllowMissingBundledTools) {
                $spaceVerification += "--allow-missing-bundled-tools"
            }
            Invoke-Checked {
                & $pythonCommand @spaceVerification
            } "PortableApps path-with-spaces verification"
        }
        finally {
            Remove-SafeBuildDirectory $spaceTestDirectory
        }
    }

    # Runtime smoke tests create Data. A distributable PortableApps package must
    # start without user state so App\DefaultData can seed it on first launch.
    $stagedDataDirectory = Join-Path $resolvedOutputDirectory "Data"
    if (Test-Path -LiteralPath $stagedDataDirectory) {
        Remove-Item -LiteralPath $stagedDataDirectory -Recurse -Force
    }
    Invoke-Checked {
        & $pythonCommand @verificationArguments --phase launcher
    } "PortableApps clean-package verification"

    if ($CreateInstaller) {
        $resolvedInstaller = Resolve-PortableAppsInstaller $PortableAppsInstaller
        $appVersion = $versionMatch.Groups[1].Value
        $generatedInstaller = Join-Path (
            Split-Path -Parent $resolvedOutputDirectory
        ) "scrcpy-launcherPortable_${appVersion}_English.paf.exe"
        if (Test-Path -LiteralPath $generatedInstaller) {
            Remove-Item -LiteralPath $generatedInstaller -Force
        }

        $installerStart = @{
            FilePath = $resolvedInstaller
            ArgumentList = ('"' + $resolvedOutputDirectory + '"')
            Wait = $true
            PassThru = $true
            WindowStyle = "Hidden"
        }
        $installerProcess = Start-Process @installerStart
        if ($installerProcess.ExitCode -ne 0) {
            throw "PortableApps.com Installer failed with exit code $($installerProcess.ExitCode)"
        }
        if (-not (Test-Path -LiteralPath $generatedInstaller -PathType Leaf)) {
            throw "PortableApps.com Installer did not create the expected package: $generatedInstaller"
        }
        $generatedItem = Get-Item -LiteralPath $generatedInstaller
        $header = [byte[]]::new(2)
        $headerStream = [System.IO.File]::OpenRead($generatedInstaller)
        try {
            $headerLength = $headerStream.Read($header, 0, 2)
        }
        finally {
            $headerStream.Dispose()
        }
        if ($generatedItem.Length -lt 1024 -or $headerLength -ne 2 -or $header[0] -ne 0x4d -or $header[1] -ne 0x5a) {
            throw "Generated PortableApps installer is not a valid Windows executable: $generatedInstaller"
        }

        $installerRoot = Split-Path -Parent $resolvedInstaller
        $sevenZip = Join-Path $installerRoot "App\7zip\7z.exe"
        if (-not (Test-Path -LiteralPath $sevenZip -PathType Leaf)) {
            throw "PortableApps installer payload verifier is missing: $sevenZip"
        }
        Invoke-Checked {
            & $sevenZip "t" $generatedInstaller "-bso0" "-bsp0"
        } "PortableApps installer payload integrity test"
        $payloadListing = & $sevenZip "l" "-slt" $generatedInstaller
        if ($LASTEXITCODE -ne 0) {
            throw "PortableApps installer payload inventory failed with exit code $LASTEXITCODE"
        }
        $listingText = $payloadListing -join "`n"
        foreach ($requiredPayload in (
            "Path = scrcpy-launcherPortable.exe",
            "Path = App\AppInfo\appinfo.ini",
            "Path = App\DefaultData\config.json",
            "Path = App\scrcpy-launcher\scrcpy-launcher.exe"
        )) {
            if (-not $listingText.Contains($requiredPayload)) {
                throw "PortableApps installer payload is missing: $requiredPayload"
            }
        }
        if ($listingText -match '(?m)^Path = Data(?:\\|$)') {
            throw "PortableApps installer payload unexpectedly contains user Data"
        }

        if ($ArtifactDirectory) {
            $resolvedArtifactDirectory = [System.IO.Path]::GetFullPath($ArtifactDirectory)
            $artifactPrefix = (Join-Path $projectRoot "dist").TrimEnd('\') + '\'
            if (-not $resolvedArtifactDirectory.StartsWith($artifactPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "PortableApps artifact output must remain beneath the project dist directory: $resolvedArtifactDirectory"
            }
            New-Item -ItemType Directory -Path $resolvedArtifactDirectory -Force | Out-Null
            $artifactPath = Join-Path $resolvedArtifactDirectory ([System.IO.Path]::GetFileName($generatedInstaller))
            Copy-Item -LiteralPath $generatedInstaller -Destination $artifactPath -Force
            Write-Host "PortableApps installer completed: $artifactPath"
        } else {
            Write-Host "PortableApps installer completed: $generatedInstaller"
        }
    }

    Write-Host "PortableApps launcher package completed: $resolvedOutputDirectory"
}
finally {
    Pop-Location
}
