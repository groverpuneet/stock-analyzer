#!/bin/bash
# Stock Analyzer Docker Watchdog
# Runs hourly via launchd to ensure containers are healthy
#
# Checks:
# 1. docker compose ps — if any container down, runs docker compose up -d
# 2. if dagster-daemon container unhealthy, restarts it
# 3. Logs all actions to ~/stock-analyzer/logs/watchdog.log

set -e

LOGFILE="/Users/puneetgrover/stock-analyzer/logs/watchdog.log"
PROJECT_DIR="/Users/puneetgrover/stock-analyzer"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
}

cd "$PROJECT_DIR"

log "=== Watchdog check starting ==="

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    log "ERROR: Docker is not running. Cannot proceed."
    exit 1
fi

# Get container status
CONTAINERS=$(docker compose ps --format json 2>/dev/null || echo "[]")

# Check if any expected containers are missing or not running
EXPECTED_CONTAINERS="dagster_daemon dagster_webserver dagster_user_code dagster_db"
ALL_HEALTHY=true

for container in $EXPECTED_CONTAINERS; do
    STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
    HEALTH=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo "unknown")

    if [ "$STATUS" != "running" ]; then
        log "Container $container is $STATUS — restarting stack"
        ALL_HEALTHY=false
        docker compose up -d 2>&1 | while read line; do log "  $line"; done
        break
    fi

    # Check health for dagster-daemon specifically
    if [ "$container" = "dagster_daemon" ] && [ "$HEALTH" = "unhealthy" ]; then
        log "Container $container is unhealthy — restarting"
        ALL_HEALTHY=false
        docker compose restart dagster-daemon 2>&1 | while read line; do log "  $line"; done
    fi
done

if [ "$ALL_HEALTHY" = true ]; then
    log "All containers healthy"
fi

# Check if Dagster webserver is responding
if curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health 2>/dev/null | grep -q "200"; then
    log "Dagster webserver responding"
else
    log "WARNING: Dagster webserver not responding on port 3000"
fi

# Check disk space (warn if < 10GB free)
FREE_GB=$(df -g "$PROJECT_DIR" | awk 'NR==2 {print $4}')
if [ "$FREE_GB" -lt 10 ]; then
    log "WARNING: Low disk space — only ${FREE_GB}GB free"
fi

log "=== Watchdog check complete ==="
