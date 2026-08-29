; SPDX-License-Identifier: GPL-3.0-only

!ifndef AppVersion
  !define AppVersion "0.8.0"
!endif
!ifndef AppVersionQuad
  !define AppVersionQuad "0.8.0.0"
!endif
!ifndef SourceDir
  !define SourceDir "..\dist\scrcpy-launcher"
!endif
!ifndef OutputDir
  !define OutputDir "..\dist\artifacts"
!endif

!define AppName "scrcpy-launcher"
!define AppExeName "scrcpy-launcher.exe"
!define AppPublisher "scrcpy-launcher contributors"
!define ConfigDir "$APPDATA\scrcpy-launcher"
!define ConfigPath "${ConfigDir}\config.json"
!define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"
!define UninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\scrcpy-launcher"
!define InnoUninstallKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{5A60C3DF-4333-45F0-A876-3DD49A85BE47}_is1"

Unicode True
Name "${AppName}"
OutFile "${OutputDir}\${AppName}-${AppVersion}-setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${AppName}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
ManifestDPIAware true

VIProductVersion "${AppVersionQuad}"
VIAddVersionKey /LANG=1033 "ProductName" "${AppName}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${AppVersion}"
VIAddVersionKey /LANG=1033 "FileDescription" "${AppName} Windows installer"
VIAddVersionKey /LANG=1033 "FileVersion" "${AppVersion}"
VIAddVersionKey /LANG=1033 "CompanyName" "${AppPublisher}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright ${AppPublisher}"

!include "LogicLib.nsh"
!include "nsis-safe-delete.nsh"
!include "MUI2.nsh"
!include "Sections.nsh"
!include "x64.nsh"

!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${AppExeName}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${AppName}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!insertmacro MUI_LANGUAGE "English"

Var InnoUninstaller
Var ExistingRunValue
Var ExpectedRunValue

!insertmacro DefineSafeRemoveTree ""
!insertmacro DefineSafeRemoveTree "un."

!macro SetSectionSelected SECTION_ID
  SectionGetFlags ${SECTION_ID} $0
  IntOp $0 $0 | ${SF_SELECTED}
  SectionSetFlags ${SECTION_ID} $0
!macroend

!macro RemoveOwnedAutostart
  ReadRegStr $ExistingRunValue HKCU "${RunKey}" "${AppName}"
  StrCpy $ExpectedRunValue '$\"$INSTDIR\${AppExeName}$\" --config $\"${ConfigPath}$\"'
  StrCmp $ExistingRunValue $ExpectedRunValue 0 +2
  DeleteRegValue HKCU "${RunKey}" "${AppName}"
!macroend

Function ConfigureRegistryView
  ${If} ${RunningX64}
    SetRegView 64
  ${EndIf}
FunctionEnd

Function EnsureTrayIsClosed
  System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "Local\scrcpy-launcher-tray") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "${AppName} is currently running.$\r$\n$\r$\nQuit it from the tray menu, then run Setup again."
    Abort
  ${EndIf}
FunctionEnd

Function un.ConfigureRegistryView
  ${If} ${RunningX64}
    SetRegView 64
  ${EndIf}
FunctionEnd

Function un.onInit
  SetShellVarContext current
  Call un.ConfigureRegistryView

  System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "Local\scrcpy-launcher-tray") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "${AppName} is currently running.$\r$\n$\r$\nQuit it from the tray menu, then run Uninstall again."
    Abort
  ${EndIf}
FunctionEnd

Section -MigrateInno
  ${If} $InnoUninstaller != ""
    DetailPrint "Removing the previous Inno Setup installation..."
    ExecWait '$\"$InnoUninstaller$\" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP \
        "The previous installer could not be removed (exit code $0). Your configuration was not changed."
      Abort
    ${EndIf}
    DeleteRegKey HKCU "${InnoUninstallKey}"
  ${EndIf}
SectionEnd

Section "${AppName} (required)" SecApplication
  SectionIn RO
  SetShellVarContext current
  Call ConfigureRegistryView

  ; Remove only directories and files owned by this application. User data is
  ; outside $INSTDIR and is intentionally untouched during upgrades.
  Push "$INSTDIR\_internal"
  Call SafeRemoveTree
  Push "$INSTDIR\licenses"
  Call SafeRemoveTree
  Push "$INSTDIR\tools"
  Call SafeRemoveTree
  Delete "$INSTDIR\${AppExeName}"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\THIRD-PARTY-NOTICES.md"
  Delete "$INSTDIR\Uninstall.exe"
  Delete "$INSTDIR\unins000.exe"
  Delete "$INSTDIR\unins000.dat"

  SetOutPath "$INSTDIR"
  File /r "${SourceDir}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${AppName}"
  CreateShortcut "$SMPROGRAMS\${AppName}\${AppName}.lnk" "$INSTDIR\${AppExeName}"

  !insertmacro RemoveOwnedAutostart
  Delete "$DESKTOP\${AppName}.lnk"

  IfFileExists "${ConfigPath}" config_ready
  IfFileExists "${ConfigPath}.bak" config_ready
  CreateDirectory "${ConfigDir}"
  SetOutPath "${ConfigDir}"
  File /oname=config.json "default-config.json"
  config_ready:

  WriteRegStr HKCU "${UninstallKey}" "DisplayName" "${AppName}"
  WriteRegStr HKCU "${UninstallKey}" "DisplayVersion" "${AppVersion}"
  WriteRegStr HKCU "${UninstallKey}" "Publisher" "${AppPublisher}"
  WriteRegStr HKCU "${UninstallKey}" "DisplayIcon" "$INSTDIR\${AppExeName},0"
  WriteRegStr HKCU "${UninstallKey}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UninstallKey}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UninstallKey}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UninstallKey}" "EstimatedSize" 70000
  WriteRegDWORD HKCU "${UninstallKey}" "NoModify" 1
  WriteRegDWORD HKCU "${UninstallKey}" "NoRepair" 1
SectionEnd

Section /o "Desktop shortcut" SecDesktop
  SetShellVarContext current
  CreateShortcut "$DESKTOP\${AppName}.lnk" "$INSTDIR\${AppExeName}"
SectionEnd

Section /o "Start ${AppName} when I sign in" SecAutostart
  Call ConfigureRegistryView
  WriteRegStr HKCU "${RunKey}" "${AppName}" \
    '$\"$INSTDIR\${AppExeName}$\" --config $\"${ConfigPath}$\"'
SectionEnd

Function .onInit
  SetShellVarContext current
  Call ConfigureRegistryView
  Call EnsureTrayIsClosed

  ReadRegStr $0 HKCU "${UninstallKey}" "InstallLocation"
  ${If} $0 != ""
    StrCmp $0 "$LOCALAPPDATA\Programs\${AppName}" nsis_path_valid
    MessageBox MB_OK|MB_ICONSTOP \
      "An existing NSIS installation was found in an unexpected location:$\r$\n$\r$\n$0$\r$\n$\r$\nUninstall it manually before continuing."
    Abort
    nsis_path_valid:
  ${EndIf}

  StrCpy $ExpectedRunValue '$\"$INSTDIR\${AppExeName}$\" --config $\"${ConfigPath}$\"'
  ReadRegStr $ExistingRunValue HKCU "${RunKey}" "${AppName}"
  ${If} $ExistingRunValue == $ExpectedRunValue
    !insertmacro SetSectionSelected ${SecAutostart}
  ${EndIf}
  IfFileExists "$DESKTOP\${AppName}.lnk" 0 +2
    !insertmacro SetSectionSelected ${SecDesktop}

  StrCpy $InnoUninstaller ""
  ReadRegStr $1 HKCU "${InnoUninstallKey}" "UninstallString"
  ${If} $1 != ""
    StrCpy $0 "$LOCALAPPDATA\Programs\${AppName}"
    StrCmp $1 '$\"$0\unins000.exe$\"' inno_path_valid
    StrCmp $1 "$0\unins000.exe" inno_path_valid
    MessageBox MB_OK|MB_ICONSTOP \
      "An existing Inno Setup registration contains an unexpected uninstall command:$\r$\n$\r$\n$1$\r$\n$\r$\nUninstall it manually before continuing."
    Abort

    inno_path_valid:
    IfFileExists "$0\unins000.exe" 0 inno_missing
    StrCpy $InnoUninstaller "$0\unins000.exe"
    StrCpy $INSTDIR $0
    Goto inno_done

    inno_missing:
    MessageBox MB_OK|MB_ICONSTOP \
      "The existing Inno Setup registration is incomplete. Uninstall the old release manually before continuing."
    Abort
  ${EndIf}

  inno_done:
FunctionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecApplication} \
    "Install ${AppName} for the current Windows account."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} \
    "Create a shortcut on the current user's desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} \
    "Start the tray application when the current user signs in. Sessions are not launched automatically."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  SetShellVarContext current
  Call un.ConfigureRegistryView

  !insertmacro RemoveOwnedAutostart
  Delete "$DESKTOP\${AppName}.lnk"
  Delete "$SMPROGRAMS\${AppName}\${AppName}.lnk"
  RMDir "$SMPROGRAMS\${AppName}"
  DeleteRegKey HKCU "${UninstallKey}"

  Push "$INSTDIR\_internal"
  Call un.SafeRemoveTree
  Push "$INSTDIR\licenses"
  Call un.SafeRemoveTree
  Push "$INSTDIR\tools"
  Call un.SafeRemoveTree
  Delete "$INSTDIR\${AppExeName}"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\THIRD-PARTY-NOTICES.md"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Also permanently remove known ${AppName} sessions, settings, configuration backups, recovery archives, and logs for this Windows account? Unknown files in these folders are preserved. Choose No to preserve all data for a future installation." \
    /SD IDNO IDNO preserve_user_data
  Delete "${ConfigPath}"
  Delete "${ConfigPath}.bak"
  Delete "${ConfigDir}\config.json.corrupt-*"
  RMDir "${ConfigDir}"
  Delete "$LOCALAPPDATA\scrcpy-launcher\tray.log"
  Delete "$LOCALAPPDATA\scrcpy-launcher\tray.log.*"
  Delete "$LOCALAPPDATA\scrcpy-launcher\settings.log"
  Delete "$LOCALAPPDATA\scrcpy-launcher\settings.log.*"
  RMDir "$LOCALAPPDATA\scrcpy-launcher"

  preserve_user_data:
SectionEnd
