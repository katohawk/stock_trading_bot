#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPERVISOR_PID_FILE="$ROOT_DIR/.server_supervisor.pid"
CHILD_PID_FILE="$ROOT_DIR/.server.pid"

stop_pid_file() {
  local pid_file="$1"
  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

stop_pid_file "$CHILD_PID_FILE"
stop_pid_file "$SUPERVISOR_PID_FILE"
