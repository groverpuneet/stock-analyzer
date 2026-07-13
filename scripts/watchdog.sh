#!/bin/bash
# Stock Analyzer Dagster Watchdog
# Runs hourly via launchd to ensure the native Dagster process is alive.
#
# Checks:
# 1. `dagster dev` process running — if not, restarts it
# 2. Dagster webserver responding on :3000 even if the process exists (catches a hung
#    process that's alive but not actually serving)
# 3. Logs all actions to ~/stock-analyzer/logs/watchdog.log
#
# NOTE: this project runs Dagster natively (`dagster dev -w workspace.yaml`), not via
# Docker — a prior version of this script only checked Docker containers, which meant it
# silently no-op'd (docker not installed) and never detected the native process dying.
# Confirmed dead 2026-07-06 -> 2026-07-12 undetected; see PROGRESS/memory notes.

set -e

LOGFILE="/Users/puneetgrover/stock-analyzer/logs/watchdog.log"
PROJECT_DIR="/Users/puneetgrover/stock-analyzer"
DAGSTER_HOME="/Users/puneetgrover/stock-analyzer/.dagster_home"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
}

cd "$PROJECT_DIR"

log "=== Watchdog check starting ==="

PROCESS_ALIVE=false
if pgrep -f "dagster dev -w workspace.yaml" > /dev/null 2>&1; then
    PROCESS_ALIVE=true
fi

WEBSERVER_OK=false
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health 2>/dev/null | grep -q "200"; then
    WEBSERVER_OK=true
fi

if [ "$PROCESS_ALIVE" = true ] && [ "$WEBSERVER_OK" = true ]; then
    log "Dagster dev process running, webserver responding on :3000"
else
    if [ "$PROCESS_ALIVE" = false ]; then
        log "ERROR: dagster dev process not found — restarting"
    else
        log "ERROR: dagster dev process alive but webserver not responding on :3000 — restarting"
    fi
    pkill -9 -f dagster 2>&1 | while read -r line; do log "  $line"; done || true
    sleep 2
    DATABASE_URL="${DATABASE_URL:-postgresql://puneetgrover@localhost/stock_analyzer}" \
        DAGSTER_HOME="$DAGSTER_HOME" \
        nohup "$PROJECT_DIR/venv310/bin/dagster" dev -w workspace.yaml \
        >> "$PROJECT_DIR/logs/dagster_dev.log" 2>&1 &
    disown
    log "Restart issued (pid $!)"
fi

# Check disk space (warn if < 10GB free)
FREE_GB=$(df -g "$PROJECT_DIR" | awk 'NR==2 {print $4}')
if [ "$FREE_GB" -lt 10 ]; then
    log "WARNING: Low disk space — only ${FREE_GB}GB free"
fi

log "=== Watchdog check complete ==="
