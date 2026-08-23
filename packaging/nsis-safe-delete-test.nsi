; SPDX-License-Identifier: GPL-3.0-only

!ifndef TestRoot
  !error "TestRoot is required"
!endif
!ifndef OutputFile
  !error "OutputFile is required"
!endif

Unicode True
SilentInstall silent
RequestExecutionLevel user
OutFile "${OutputFile}"

!include "LogicLib.nsh"
!include "nsis-safe-delete.nsh"
!insertmacro DefineSafeRemoveTree ""

Section
  Push "${TestRoot}"
  Call SafeRemoveTree
SectionEnd
