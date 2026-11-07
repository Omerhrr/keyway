#!/bin/bash
# Keyway daemon helper: starts a long-lived service detached from the tool shell.
# usage: daemon.sh <name> <workdir> <command...>
NAME="$1"; shift
WORKDIR="$1"; shift
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZDIR="$ROOT/.zscripts"
mkdir -p "$ZDIR"
LOG="$ZDIR/daemon-$NAME.log"
PIDFILE="$ZDIR/daemon-$NAME.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "[$NAME] already running (pid $(cat "$PIDFILE"))"
  exit 0
fi
cd "$WORKDIR" || exit 1
setsid nohup "$@" >>"$LOG" 2>&1 </dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
exit 0
