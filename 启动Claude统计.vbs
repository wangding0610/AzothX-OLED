Option Explicit
Dim shell, files, root
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.Run "wscript.exe //B //NoLogo """ & files.BuildPath(root, "tools\clock_silent.vbs") & """ claude", 0, False
