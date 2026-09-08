@echo off
setlocal
rem Find a Python that actually works, then run the script the caller named.
rem
rem ⛔ WHY THIS EXISTS BESIDE run.sh, WHICH DOES THE SAME JOB:
rem `bash` on a Windows PATH is usually NOT Git Bash. Measured 2026-08-26 from
rem PowerShell: `bash` resolved to %LOCALAPPDATA%\Microsoft\WindowsApps\bash.exe, the
rem WSL launcher stub, which prints "Windows Subsystem for Linux has no installed
rem distributions" and fails. Claude Code invokes its own bash and is fine; a VS Code
rem task runs through the user's default shell and is not. Same shape as the python3
rem Store stub: the command resolves, so every "is it installed" check passes, and only
rem running it reveals the truth.
rem
rem So anything launched by the EDITOR goes through this file, and anything launched by
rem Claude Code goes through run.sh.
rem
rem Each candidate is EXECUTED before being trusted, for the same reason.
set "PYBIN="
for %%C in (python.exe py.exe python3.exe) do (
  if not defined PYBIN (
    %%C -c "import sys" >nul 2>&1 && set "PYBIN=%%C"
  )
)
if not defined PYBIN (
  echo dispatch-guard: no working Python interpreter found on PATH.
  exit /b 0
)
rem Without this a non-ASCII character is mangled by the console codepage, and a
rem double-byte codepage swallows the byte after it.
set PYTHONIOENCODING=utf-8
"%PYBIN%" %*
