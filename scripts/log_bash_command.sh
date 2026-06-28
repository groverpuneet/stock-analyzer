#!/usr/bin/env bash
# PostToolUse hook — logs every Bash command Claude Code runs to logs/claude_code_commands.log
# Receives hook input JSON via stdin with fields: tool_name, tool_input, tool_result
#
# Format: [2026-06-27 09:15:32] CMD: <command> | EXIT: <code>
#
# Exit codes: 0 = pass through (don't block anything)

set -euo pipefail

LOG_FILE="${CLAUDE_PROJECT_DIR:-$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel 2>/dev/null || echo ".")}/logs/claude_code_commands.log"
mkdir -p "$(dirname "$LOG_FILE")"

# Read stdin hook JSON
input=$(cat)

# Extract the command (tool_input.command)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
if [ -z "$cmd" ]; then
  exit 0  # Not a Bash call or no command field — pass through silently
fi

# Determine exit code from tool_result
# tool_result can be: a JSON object {output, isError, interrupted} or a plain string
tool_result=$(printf '%s' "$input" | jq -r '.tool_result // empty' 2>/dev/null || true)

exit_code="0"
if printf '%s' "$tool_result" | jq -e '.isError == true' > /dev/null 2>&1; then
  # It's a JSON object with isError=true — extract numeric exit code from output text if present
  output_text=$(printf '%s' "$tool_result" | jq -r '.output // ""' 2>/dev/null || true)
  if [[ "$output_text" =~ Exit\ code[[:space:]]*:?[[:space:]]*([0-9]+) ]]; then
    exit_code="${BASH_REMATCH[1]}"
  else
    exit_code="1"  # Non-zero but code not parseable
  fi
elif [[ "$tool_result" =~ Exit\ code[[:space:]]*:?[[:space:]]*([0-9]+) ]]; then
  # Plain string with "Exit code N"
  exit_code="${BASH_REMATCH[1]}"
fi

# Collapse multi-line commands and long commands for the log
cmd_single=$(printf '%s' "$cmd" | tr '\n' ' ' | sed 's/  */ /g' | cut -c1-200)

# Append log entry
printf '[%s] CMD: %s | EXIT: %s\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" \
  "$cmd_single" \
  "$exit_code" \
  >> "$LOG_FILE"

exit 0
