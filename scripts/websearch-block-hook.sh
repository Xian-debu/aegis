#!/usr/bin/env bash
# PreToolUse hook: blocks WebSearch/WebFetch and reminds to use ws
# Reads tool_name and tool_input from stdin JSON, outputs blocking decision.
# Uses python3 for JSON parsing (stdlib, always available).
set -euo pipefail

INPUT=$(cat)
TOOL=$(python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" <<< "$INPUT")

if [ "$TOOL" = "WebSearch" ] || [ "$TOOL" = "WebFetch" ]; then
    QUERY=$(python3 -c "
import sys, json
d = json.load(sys.stdin)
ti = d.get('tool_input', {})
print(ti.get('query', ti.get('url', '')))
" <<< "$INPUT")

    cat <<EOJSON
{
  "continue": false,
  "stopReason": "WebSearch/WebFetch disabled. Use Bash: ws \"$QUERY\"",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Use ws command: ws \"$QUERY\""
  }
}
EOJSON
    exit 0
fi

# Allow all other tools
echo '{"continue": true}'
exit 0
