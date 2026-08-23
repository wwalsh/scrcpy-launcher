; SPDX-License-Identifier: GPL-3.0-only

; Define an installer or uninstaller tree-removal function that never follows
; Windows reparse points. The caller must still pass only a validated app-owned
; root path.
!macro DefineSafeRemoveTree PREFIX
Function ${PREFIX}SafeRemoveTree
  Exch $R0
  Push $R1
  Push $R2
  Push $R3
  Push $R4

  System::Call 'kernel32::GetFileAttributesW(w r10) i.r14'
  ${If} $R4 == -1
    Goto safe_remove_done
  ${EndIf}

  ; FILE_ATTRIBUTE_REPARSE_POINT: remove the link itself without enumerating it.
  IntOp $R3 $R4 & 0x400
  ${If} $R3 != 0
    IntOp $R3 $R4 & 0x10
    ${If} $R3 != 0
      RMDir "$R0"
    ${Else}
      Delete "$R0"
    ${EndIf}
    Goto safe_remove_done
  ${EndIf}

  ; Plain files are deleted directly. Only ordinary directories are traversed.
  IntOp $R3 $R4 & 0x10
  ${If} $R3 == 0
    Delete "$R0"
    Goto safe_remove_done
  ${EndIf}

  FindFirst $R1 $R2 "$R0\*"
  safe_remove_loop:
    StrCmp $R2 "" safe_remove_close
    StrCmp $R2 "." safe_remove_next
    StrCmp $R2 ".." safe_remove_next
    Push "$R0\$R2"
    Call ${PREFIX}SafeRemoveTree
  safe_remove_next:
    FindNext $R1 $R2
    Goto safe_remove_loop
  safe_remove_close:
    FindClose $R1
    RMDir "$R0"

  safe_remove_done:
  Pop $R4
  Pop $R3
  Pop $R2
  Pop $R1
  Pop $R0
FunctionEnd
!macroend
