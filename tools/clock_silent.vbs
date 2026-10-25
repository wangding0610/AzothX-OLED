Option Explicit
Dim shell, files, root, config, pythonw, item, action, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(files.GetParentFolderName(WScript.ScriptFullName))
If WScript.Arguments.Count <> 1 Then WScript.Quit 2
action = LCase(WScript.Arguments(0))
If action <> "start" And action <> "stop" And action <> "codex" And action <> "claude" Then WScript.Quit 2
config = files.BuildPath(root, ".runtime\clock-pythonw.txt")
pythonw = ""
If files.FileExists(config) Then
    Dim stream
    Set stream = files.OpenTextFile(config, 1, False, -1)
    pythonw = Trim(stream.ReadAll)
    stream.Close
End If
If Not files.FileExists(pythonw) Then
    pythonw = ""
    For Each item In Split(shell.Environment("PROCESS")("PATH"), ";")
        item = Replace(item, """", "")
        If Len(item) > 0 Then
            If files.FileExists(files.BuildPath(item, "pythonw.exe")) Then
                pythonw = files.BuildPath(item, "pythonw.exe")
                Exit For
            End If
        End If
    Next
End If
If Len(pythonw) = 0 Then
    MsgBox "Pythonw.exe was not found. Install Python and the project dependencies first.", 48, "Beijing clock"
    WScript.Quit 1
End If
command = """" & pythonw & """ """ & files.BuildPath(root, "tools\clock_service.py") & """ " & action
shell.Run command, 0, False
