#!/bin/sh
# Find a Python that actually works, then run the script the caller named.
#
# ⛔ Why this file exists instead of putting `python` straight into hooks.json:
# the obvious interpreter name is wrong on both platforms, in opposite directions.
#   - On Unix there is often no bare `python` at all, only `python3`.
#   - On Windows `python3` IS on PATH and is a TRAP: it resolves to the Microsoft
#     Store alias stub, so `command -v python3` succeeds, but running it prints
#     "Python was not found..." and exits 49. A caller that only checks whether the
#     command resolves gets a confident wrong answer.
# So each candidate is EXECUTED before being trusted. That is the only check that
# tells a real interpreter from a stub.
#
# PYTHONIOENCODING=utf-8 is not cosmetics: without it a non-ASCII byte in a hook
# payload is mangled by the console codepage (cp950 on some Windows machines), and a
# double-byte codepage swallows the following byte too.
#
# Exits 0 when no interpreter is found. A hook that cannot run must not block work.
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then
    PYBIN="$c"
    break
  fi
done
if [ -z "$PYBIN" ]; then
  exit 0
fi
PYTHONIOENCODING=utf-8 exec "$PYBIN" "$@"
