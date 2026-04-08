#!/usr/bin/env bash
# purpose:  Log subagent completion and surface result summary
# when:     SubagentStop hook — fires after a subagent finishes
# inputs:   JSON via stdin with subagent result details
# outputs:  JSON with additionalContext summarising outcome
# risk:     safe
# ESCALATION: none
set -euo pipefail

# shellcheck source=.github/hooks/scripts/lib-hooks.sh
source "$(dirname "$0")/lib-hooks.sh"

INPUT=$(cat)

# Extract subagent name if available (python3 for robust JSON parsing)
AGENT_NAME=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agentName','unknown'))" 2>/dev/null) || AGENT_NAME="unknown"
[[ -z "$AGENT_NAME" ]] && AGENT_NAME="unknown"

# Build summary context
CONTEXT="Subagent ${AGENT_NAME} completed. Review results before continuing."

# JSON-escape the context
CONTEXT_ESC=$(json_escape "$CONTEXT")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStop",
    "additionalContext": "${CONTEXT_ESC}"
  }
}
EOF
