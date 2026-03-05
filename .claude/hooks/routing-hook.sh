#!/bin/bash
# TANEBI routing hook
# Classifies user input as TANEBI (build/create) or DIRECT (conversation)
# Uses claude -p with haiku, minimal config for speed

INPUT=$(cat)
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty')

if [ -z "$PROMPT" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[DIRECT]"}}'
  exit 0
fi

DECISION=$(echo "Is this a request to build, create, or implement something? Input: $PROMPT" | env -u CLAUDECODE claude -p \
  --model haiku \
  --disable-slash-commands \
  --tools "" \
  --no-session-persistence \
  --setting-sources "" \
  --system-prompt "Output only YES or NO." \
  2>/dev/null)

if echo "$DECISION" | grep -qi "YES"; then
  echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[TANEBI] This is a build request. Use tanebi new to start the flow."}}'
else
  echo '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"[DIRECT]"}}'
fi

exit 0
