#!/usr/bin/env bash
# parse_plan.sh — plan.md のYAMLからサブタスク情報をTSV形式で出力
# 出力: subtask_id\tpersona\twave\tdescription\tdepends_on
set -eu
set -o pipefail

PLAN_FILE="${1:?Usage: parse_plan.sh <plan.md>}"

if [[ ! -f "$PLAN_FILE" ]]; then
  echo "ERROR: File not found: $PLAN_FILE" >&2
  exit 1
fi

# Strategy 1: yq (if available)
if command -v yq &>/dev/null; then
  yq -r '.plan.subtasks[] | [.id, .persona, .wave, .description, (.depends_on // [] | join(","))] | @tsv' "$PLAN_FILE"
  exit 0
fi

# Strategy 2: python3 (standard on macOS, no PyYAML dependency)
if command -v python3 &>/dev/null; then
  python3 - "$PLAN_FILE" << 'PYEOF'
import sys, re

plan_file = sys.argv[1]
with open(plan_file) as f:
    content = f.read()

# Split into subtask blocks by "- id:" entries
blocks = re.split(r'(?=^\s*- id:)', content, flags=re.MULTILINE)

for block in blocks:
    id_m = re.search(r'(?:^|\n)\s*-?\s*id:\s*(.+)', block)
    if not id_m:
        continue
    sid = id_m.group(1).strip().strip('"').strip("'")

    persona_m = re.search(r'persona:\s*(.+)', block)
    persona = persona_m.group(1).strip().strip('"').strip("'").split('#')[0].strip() if persona_m else ""

    wave_m = re.search(r'wave:\s*(.+)', block)
    wave = wave_m.group(1).strip().strip('"').strip("'").split('#')[0].strip() if wave_m else ""

    desc_m = re.search(r'description:\s*(.+)', block)
    desc = desc_m.group(1).strip().strip('"').strip("'") if desc_m else ""

    deps_m = re.search(r'depends_on:\s*\[([^\]]*)\]', block)
    if deps_m:
        deps_raw = deps_m.group(1).strip()
        deps_str = ",".join(d.strip().strip('"').strip("'") for d in deps_raw.split(",") if d.strip())
    else:
        deps_str = ""

    print(f"{sid}\t{persona}\t{wave}\t{desc}\t{deps_str}")
PYEOF
  exit 0
fi

# Strategy 3: grep/awk fallback
awk '
BEGIN { OFS="\t"; id=""; persona=""; wave=""; desc=""; deps="" }
/^[[:space:]]*- id:/ {
  if (id != "") print id, persona, wave, desc, deps
  gsub(/^[[:space:]]*- id:[[:space:]]*/, ""); gsub(/["\047]/, "")
  id = $0; persona=""; wave=""; desc=""; deps=""
}
/^[[:space:]]*persona:/ {
  gsub(/^[[:space:]]*persona:[[:space:]]*/, ""); gsub(/["\047]/, "")
  persona = $0
}
/^[[:space:]]*wave:/ {
  gsub(/^[[:space:]]*wave:[[:space:]]*/, ""); gsub(/["\047]/, "")
  wave = $0
}
/^[[:space:]]*description:/ {
  gsub(/^[[:space:]]*description:[[:space:]]*/, ""); gsub(/["\047]/, ""); gsub(/"/, "")
  desc = $0
}
/^[[:space:]]*depends_on:.*\[/ {
  gsub(/^[[:space:]]*depends_on:[[:space:]]*\[/, ""); gsub(/\].*/, ""); gsub(/[[:space:]]/, "")
  deps = $0
}
END { if (id != "") print id, persona, wave, desc, deps }
' "$PLAN_FILE"
