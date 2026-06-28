#!/bin/bash
# docker_watchdog.sh — keep the Dagster stack up. Run hourly by launchd
# (com.stockanalyzer.watchdog). If any of the 4 containers is not running,
# bring the stack back up. Logs to logs/watchdog.log.
set -u

PROJECT="/Users/puneetgrover/stock-analyzer"
LOG="$PROJECT/logs/watchdog.log"
COMPOSE="/usr/local/bin/docker"   # adjust if docker is elsewhere
[ -x "$COMPOSE" ] || COMPOSE="$(command -v docker || echo docker)"

mkdir -p "$PROJECT/logs"
ts() { date '+%Y-%m-%d %H:%M:%S'; }

cd "$PROJECT" || { echo "$(ts) FATAL: project dir missing" >> "$LOG"; exit 1; }

# how many of our 4 services are currently running?
running=$("$COMPOSE" compose ps --services --filter status=running 2>/dev/null | grep -cE 'dagster-db|user-code|dagster-webserver|dagster-daemon')

if [ "${running:-0}" -lt 4 ]; then
  echo "$(ts) only $running/4 dagster containers up — running 'docker compose up -d'" >> "$LOG"
  "$COMPOSE" compose up -d >> "$LOG" 2>&1
  echo "$(ts) recovery attempt done (exit $?)" >> "$LOG"
else
  echo "$(ts) ok — 4/4 dagster containers running" >> "$LOG"
fi
