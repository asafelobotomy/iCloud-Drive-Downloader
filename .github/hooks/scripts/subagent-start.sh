#!/usr/bin/env bash
# purpose:  Inject subagent governance context when a subagent is spawned
# when:     SubagentStart hook — fires before a subagent begins work
# inputs:   JSON via stdin with subagent details
# outputs:  JSON with additionalContext reminding depth limit and protocols
# risk:     safe
# ESCALATION: none
set -euo pipefail

# shellcheck source=.github/hooks/scripts/lib-hooks.sh
source "$(dirname "$0")/lib-hooks.sh"

INPUT=$(cat)

# Extract subagent name if available (python3 for robust JSON parsing)
AGENT_NAME=$(printf '%s' "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agentName','unknown'))" 2>/dev/null) || AGENT_NAME="unknown"
[[ -z "$AGENT_NAME" ]] && AGENT_NAME="unknown"

# Build governance context
CONTEXT="Subagent governance: max depth 2. Inherited protocols: PDCA cycle, Tool Protocol, Skill Protocol. Agent: ${AGENT_NAME}."

# JSON-escape the context
CONTEXT_ESC=$(json_escape "$CONTEXT")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SubagentStart",
    "additionalContext": "${CONTEXT_ESC}"
  }
}
EOF
