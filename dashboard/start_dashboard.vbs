' Start the Hydra dashboard watchdog fully detached, using the project venv
' python so all packages (numpy, piexif, imageio-ffmpeg, etc.) resolve.
' Bare "python" used to resolve to the Windows Store Python which lacks
' those packages and crashed simple_app on import.
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run """..\venv\Scripts\python.exe"" run_dashboard.py", 0, False
