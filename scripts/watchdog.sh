#!/bin/bash
# Stock Analyzer Dagster Watchdog
# Runs hourly via launchd to ensure the native Dagster process is alive, and posts a
# heartbeat per component to the shared cross-project Supabase `heartbeats` table.
#
# Checks:
# 1. `dagster dev` process running — if not, restarts it
# 2. Dagster webserver responding on :3000 even if the process exists (catches a hung
#    process that's alive but not actually serving)
# 3. backend/frontend/tunnel/scheduler/postgres liveness (no restart action, just report)
# 4. Logs all actions to ~/stock-analyzer/logs/watchdog.log
#
# NOTE: this project runs Dagster natively (`dagster dev -w workspace.yaml`), not via
# Docker — a prior version of this script only checked Docker containers, which meant it
# silently no-op'd (docker not installed) and never detected the native process dying.
# Confirmed dead 2026-07-06 -> 2026-07-12 undetected; see PROGRESS/memory notes.
#
# Heartbeats: posted via PostgREST using the ANON (publishable) Supabase key, read from
# untracked .env.heartbeat (git-ignored by the existing `.env.*` pattern). RLS on
# `heartbeats` grants anon INSERT-only — this key can never read or tamper with anything,
# so it's safe to keep in a plain file here. Each component check is independent: one
# failing check (or a heartbeat POST failing) must not stop the others from running.

LOGFILE="/Users/puneetgrover/stock-analyzer/logs/watchdog.log"
PROJECT_DIR="/Users/puneetgrover/stock-analyzer"
DAGSTER_HOME="/Users/puneetgrover/stock-analyzer/.dagster_home"
ENV_HEARTBEAT="$PROJECT_DIR/.env.heartbeat"
PG_BIN="/opt/homebrew/opt/postgresql@15/bin"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOGFILE"
}

cd "$PROJECT_DIR"

# --- Heartbeat plumbing ------------------------------------------------------
# Parse KEY=VALUE lines robustly (not `source`d — a stray space after `=` would make
# the shell try to execute the value as a command).
_hb_get() {
    python3 -c "
import sys
key = sys.argv[1]
try:
    with open(sys.argv[2]) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + '='):
                print(line.split('=', 1)[1].strip())
                break
except FileNotFoundError:
    pass
" "$1" "$ENV_HEARTBEAT"
}

HEARTBEAT_PROJECT_REF=$(_hb_get HEARTBEAT_PROJECT_REF)
HEARTBEAT_ANON_KEY=$(_hb_get HEARTBEAT_ANON_KEY)

# post_heartbeat COMPONENT STATUS JSON_DETAIL
post_heartbeat() {
    local component="$1" status="$2" detail="$3"
    if [ -z "$HEARTBEAT_PROJECT_REF" ] || [ -z "$HEARTBEAT_ANON_KEY" ]; then
        log "  heartbeat[$component]: SKIPPED (missing .env.heartbeat values)"
        return
    fi
    local body http_code
    body=$(printf '{"project":"stock-analyzer","component":"%s","status":"%s","detail":%s}' \
        "$component" "$status" "${detail:-null}")
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        "https://${HEARTBEAT_PROJECT_REF}.supabase.co/rest/v1/heartbeats" \
        -H "apikey: ${HEARTBEAT_ANON_KEY}" -H "Authorization: Bearer ${HEARTBEAT_ANON_KEY}" \
        -H "Content-Type: application/json" -H "Prefer: return=minimal" \
        -d "$body" --max-time 10 2>/dev/null)
    if [ "$http_code" = "201" ]; then
        log "  heartbeat[$component]: posted ($status), HTTP $http_code"
    else
        log "  heartbeat[$component]: FAILED to post, HTTP $http_code"
    fi
}

log "=== Watchdog check starting ==="

# --- 1. Dagster (with restart action) ----------------------------------------
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
    post_heartbeat "dagster" "up" '{"restarted":false}'
else
    if [ "$PROCESS_ALIVE" = false ]; then
        log "ERROR: dagster dev process not found — restarting"
    else
        log "ERROR: dagster dev process alive but webserver not responding on :3000 — restarting"
    fi
    ( pkill -9 -f dagster 2>&1 | while read -r line; do log "  $line"; done ) || true
    sleep 2
    DATABASE_URL="${DATABASE_URL:-postgresql://puneetgrover@localhost/stock_analyzer}" \
        DAGSTER_HOME="$DAGSTER_HOME" \
        nohup "$PROJECT_DIR/venv310/bin/dagster" dev -w workspace.yaml \
        >> "$PROJECT_DIR/logs/dagster_dev.log" 2>&1 &
    disown
    log "Restart issued (pid $!)"
    post_heartbeat "dagster" "down" '{"restarted":true}'
fi

# --- 2. Backend (FastAPI :8009) ----------------------------------------------
( BACKEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://localhost:8009/api/health 2>/dev/null)
  if [ "$BACKEND_CODE" = "200" ]; then
      log "backend: responding (HTTP 200)"
      post_heartbeat "backend" "up" "{\"http_code\":$BACKEND_CODE}"
  else
      log "WARNING: backend not responding (HTTP ${BACKEND_CODE:-none})"
      post_heartbeat "backend" "down" "{\"http_code\":\"${BACKEND_CODE:-none}\"}"
  fi
) || log "  backend check itself errored"

# --- 3. Frontend (Vite dev server :5173) -------------------------------------
( FRONTEND_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://localhost:5173 2>/dev/null)
  if [ "$FRONTEND_CODE" = "200" ]; then
      log "frontend: responding (HTTP 200)"
      post_heartbeat "frontend" "up" "{\"http_code\":$FRONTEND_CODE}"
  else
      log "WARNING: frontend not responding (HTTP ${FRONTEND_CODE:-none})"
      post_heartbeat "frontend" "down" "{\"http_code\":\"${FRONTEND_CODE:-none}\"}"
  fi
) || log "  frontend check itself errored"

# --- 4. Tunnel (ngrok) --------------------------------------------------------
# Process liveness is the definitive up/down signal (per plist, tunnels :5173). The public
# URL check is best-effort/informational only — sandboxed/restricted networks can fail this
# even when the tunnel is genuinely fine, so it never flips status on its own.
( if pgrep -f ngrok > /dev/null 2>&1; then
      PUBLIC_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 https://avalanche-joining-yin.ngrok-free.dev 2>/dev/null)
      log "tunnel: ngrok process alive (public URL check: HTTP ${PUBLIC_CODE:-none})"
      post_heartbeat "tunnel" "up" "{\"public_http_code\":\"${PUBLIC_CODE:-none}\"}"
  else
      log "WARNING: ngrok process not found"
      post_heartbeat "tunnel" "down" '{}'
  fi
) || log "  tunnel check itself errored"

# --- 5. Scheduler (launchd KeepAlive daemon) ---------------------------------
( SCHED_STATUS=$(launchctl list com.stockanalyzer.scheduler 2>/dev/null)
  SCHED_PID=$(echo "$SCHED_STATUS" | grep -o '"PID" = [0-9]*' | grep -o '[0-9]*')
  SCHED_EXIT=$(echo "$SCHED_STATUS" | grep -o '"LastExitStatus" = [0-9]*' | grep -o '[0-9]*')
  if [ -n "$SCHED_PID" ]; then
      log "scheduler: running (pid $SCHED_PID)"
      post_heartbeat "scheduler" "up" "{\"pid\":$SCHED_PID}"
  elif [ -n "$SCHED_EXIT" ] && [ "$SCHED_EXIT" != "0" ]; then
      log "WARNING: scheduler not running, last exit status $SCHED_EXIT (possible crash loop — not auto-fixed, see watchdog.sh directive notes)"
      post_heartbeat "scheduler" "degraded" "{\"last_exit_status\":$SCHED_EXIT}"
  else
      log "WARNING: scheduler status unclear (not loaded, or launchctl output unparsed)"
      post_heartbeat "scheduler" "down" '{}'
  fi
) || log "  scheduler check itself errored"

# --- 6. Postgres --------------------------------------------------------------
( if "$PG_BIN/pg_isready" -q 2>/dev/null; then
      log "postgres: ready"
      post_heartbeat "postgres" "up" '{}'
  else
      log "WARNING: postgres not ready (pg_isready failed)"
      post_heartbeat "postgres" "down" '{}'
  fi
) || log "  postgres check itself errored"

# Check disk space (warn if < 10GB free)
FREE_GB=$(df -g "$PROJECT_DIR" | awk 'NR==2 {print $4}')
if [ "$FREE_GB" -lt 10 ]; then
    log "WARNING: Low disk space — only ${FREE_GB}GB free"
fi

log "=== Watchdog check complete ==="
