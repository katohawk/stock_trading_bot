#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5555}"
MAX_RESTARTS="${MAX_RESTARTS:-3}"
RESTART_DELAY="${RESTART_DELAY:-10}"
FOREGROUND="${FOREGROUND:-0}"
DAEMONIZED="${RUN_SERVER_DAEMONIZED:-0}"

LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
APP_LOG="$LOG_DIR/server.log"
SUPERVISOR_LOG="$LOG_DIR/server_supervisor.log"
PID_FILE="$ROOT_DIR/.server_supervisor.pid"
CHILD_PID_FILE="$ROOT_DIR/.server.pid"

mkdir -p "$LOG_DIR"

is_pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

if [ -f "$PID_FILE" ]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if is_pid_alive "$existing_pid"; then
    printf 'Supervisor already running with pid=%s\n' "$existing_pid"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [ -f "$CHILD_PID_FILE" ]; then
  existing_child_pid="$(cat "$CHILD_PID_FILE" 2>/dev/null || true)"
  if ! is_pid_alive "$existing_child_pid"; then
    rm -f "$CHILD_PID_FILE"
  fi
fi

if [ "$FOREGROUND" != "1" ] && [ "$DAEMONIZED" != "1" ]; then
  RUN_SERVER_DAEMONIZED=1 nohup "$0" "$@" >/dev/null 2>&1 < /dev/null &
  printf 'Supervisor started in background. pid=%s\n' "$!"
  exit 0
fi

echo "$$" > "$PID_FILE"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$SUPERVISOR_LOG"
}

cleanup() {
  rm -f "$PID_FILE" "$CHILD_PID_FILE"
}

trap cleanup EXIT INT TERM HUP

restart_count=0

log "Supervisor started. host=$HOST port=$PORT max_restarts=$MAX_RESTARTS restart_delay=${RESTART_DELAY}s"

while true; do
  "$PYTHON_BIN" server.py --host "$HOST" --port "$PORT" >> "$APP_LOG" 2>&1 &
  child_pid=$!
  echo "$child_pid" > "$CHILD_PID_FILE"
  log "Started server.py with pid=$child_pid"

  wait "$child_pid"
  exit_code=$?
  rm -f "$CHILD_PID_FILE"

  if [ "$exit_code" -eq 0 ]; then
    log "server.py exited normally with code=0; supervisor stopping"
    break
  fi

  if [ "$restart_count" -ge "$MAX_RESTARTS" ]; then
    log "server.py exited with code=$exit_code; reached max restarts ($MAX_RESTARTS), supervisor stopping"
    break
  fi

  restart_count=$((restart_count + 1))
  log "server.py exited with code=$exit_code; restart $restart_count/$MAX_RESTARTS in ${RESTART_DELAY}s"
  sleep "$RESTART_DELAY"
done
