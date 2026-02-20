#!/usr/bin/env bash
# scripts/estimate_cost.sh — トークン数推定ユーティリティ
# Usage:
#   bash scripts/estimate_cost.sh "some text"
#   bash scripts/estimate_cost.sh path/to/file.txt
#   echo "text" | bash scripts/estimate_cost.sh -
#
# 推定式: トークン ≈ 文字数 ÷ 4 (英語基準)
# 日本語テキストは文字数 ÷ 2 で推定

set -euo pipefail

INPUT="${1:-}"

if [ -z "$INPUT" ]; then
  echo "Usage: estimate_cost.sh <text|file|->" >&2
  echo "  -         : read from stdin" >&2
  echo "  <file>    : read from file" >&2
  echo "  <text>    : estimate given text" >&2
  exit 1
fi

# Get text content
if [ "$INPUT" = "-" ]; then
  TEXT=$(cat)
elif [ -f "$INPUT" ]; then
  TEXT=$(cat "$INPUT")
else
  TEXT="$INPUT"
fi

python3 - "$INPUT" <<PYEOF
import sys, re

# Get text from stdin (passed via shell heredoc trick)
text = """$(echo "$TEXT" | sed 's/\\/\\\\/g; s/"""/\\"\\"\\"\\"/g')"""

char_count = len(text)

# Detect Japanese content ratio
jp_chars = len(re.findall(r'[\u3000-\u9fff\uff00-\uffef]', text))
jp_ratio = jp_chars / max(char_count, 1)

# Token estimation: JP ~2 chars/token, EN ~4 chars/token
if jp_ratio > 0.3:
    tokens = char_count // 2
    note = f"Japanese-heavy (JP ratio: {jp_ratio:.0%})"
else:
    tokens = char_count // 4
    note = f"Latin-heavy (JP ratio: {jp_ratio:.0%})"

print(f"Characters : {char_count:,}")
print(f"Est. tokens: {tokens:,}  ({note})")
print(tokens)
PYEOF
