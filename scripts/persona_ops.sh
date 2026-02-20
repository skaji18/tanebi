#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TANEBI_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACTIVE_DIR="$TANEBI_ROOT/personas/active"
HISTORY_DIR="$TANEBI_ROOT/personas/history"

usage() {
    cat <<'USAGE'
Usage: persona_ops.sh <command> [args...]

Commands:
  copy <src_persona> <new_name>                         Copy persona (Portable granularity)
  merge <persona_a> <persona_b> <new_name> [weight_a]   Merge two personas (weighted)
  snapshot <persona>                                     Save snapshot to history
  list                                                   List active personas
  restore <snapshot_path>                                Restore from snapshot
USAGE
    exit 1
}

[ $# -lt 1 ] && usage

CMD="$1"; shift

case "$CMD" in

# ============================================================
# copy — Portable granularity (identity + knowledge + behavior)
# ============================================================
copy)
    [ $# -lt 2 ] && { echo "Error: Usage: persona_ops.sh copy <src_persona> <new_name>" >&2; exit 1; }
    SRC="$1"; NEW_NAME="$2"
    SRC_FILE="$ACTIVE_DIR/${SRC}.yaml"
    DST_FILE="$ACTIVE_DIR/${NEW_NAME}.yaml"
    [ ! -f "$SRC_FILE" ] && { echo "Error: Source persona not found: $SRC_FILE" >&2; exit 1; }
    [ -f "$DST_FILE" ] && { echo "Error: Target persona already exists: $DST_FILE" >&2; exit 1; }

    python3 - "$SRC_FILE" "$DST_FILE" "$NEW_NAME" "$SRC" <<'PYEOF'
import sys, re
from datetime import datetime

src_file, dst_file, new_name, src_name = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

with open(src_file) as f:
    lines = f.readlines()

# Remove performance and evolution sections (Portable = identity + knowledge + behavior)
output_lines = []
skip_section = False

for raw_line in lines:
    line = raw_line.rstrip('\n')
    stripped = line.strip()
    indent = len(line) - len(line.lstrip()) if stripped else -1

    # Detect performance: or evolution: sections (indent=2, direct children of persona:)
    if indent == 2 and re.match(r'(performance|evolution):', stripped):
        skip_section = True
        continue

    if skip_section:
        if not stripped:
            continue  # skip blank lines within section
        if indent > 2:
            continue  # still inside skipped section
        else:
            skip_section = False

    output_lines.append(line)

content = '\n'.join(output_lines)

# Ensure trailing newline
if not content.endswith('\n'):
    content += '\n'

# Update persona id
content = re.sub(r'(^\s+id:\s*)"[^"]*"', rf'\1"{new_name}"', content, count=1, flags=re.MULTILINE)

# Update origin to "copied"
content = re.sub(r'(origin:\s*)\S+', r'\1copied', content)

# Update version to 1
content = re.sub(r'(^\s+version:\s*)\d+', r'\g<1>1', content, count=1, flags=re.MULTILINE)

# Update parent_version
content = re.sub(r'(parent_version:\s*)\S+', rf'\1"{src_name}"', content)

# Update lineage
content = re.sub(r'(lineage:\s*)\[.*?\]', rf'\1["{src_name}"]', content)

# Update created_at
now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
content = re.sub(r'(created_at:\s*)"[^"]*"', rf'\1"{now}"', content)

# Update granularity comment
content = re.sub(
    r'^#.*granularity:.*$',
    f'# granularity: portable (copied from {src_name})',
    content, count=1, flags=re.MULTILINE
)

# Reset task_count to 0 in all domains
content = re.sub(r'(task_count:\s*)\d+', r'\g<1>0', content)

with open(dst_file, 'w') as f:
    f.write(content)

print(f"Copied {src_name} -> {new_name} (Portable granularity)")
print(f"  Source: {src_file}")
print(f"  Target: {dst_file}")
PYEOF
    ;;

# ============================================================
# merge — Weighted combination of two personas
# ============================================================
merge)
    [ $# -lt 3 ] && { echo "Error: Usage: persona_ops.sh merge <persona_a> <persona_b> <new_name> [weight_a]" >&2; exit 1; }
    PA="$1"; PB="$2"; NEW_NAME="$3"; WEIGHT="${4:-0.5}"
    PA_FILE="$ACTIVE_DIR/${PA}.yaml"
    PB_FILE="$ACTIVE_DIR/${PB}.yaml"
    DST_FILE="$ACTIVE_DIR/${NEW_NAME}.yaml"
    [ ! -f "$PA_FILE" ] && { echo "Error: Persona A not found: $PA_FILE" >&2; exit 1; }
    [ ! -f "$PB_FILE" ] && { echo "Error: Persona B not found: $PB_FILE" >&2; exit 1; }
    [ -f "$DST_FILE" ] && { echo "Error: Target persona already exists: $DST_FILE" >&2; exit 1; }

    python3 - "$PA_FILE" "$PB_FILE" "$DST_FILE" "$NEW_NAME" "$WEIGHT" "$PA" "$PB" <<'PYEOF'
import sys, re
from datetime import datetime

pa_file, pb_file, dst_file = sys.argv[1], sys.argv[2], sys.argv[3]
new_name, weight_a_str = sys.argv[4], sys.argv[5]
pa_name, pb_name = sys.argv[6], sys.argv[7]
weight_a = float(weight_a_str)
weight_b = 1.0 - weight_a

def extract_field(content, field_name):
    """Extract a simple scalar field value."""
    m = re.search(rf'^\s+{field_name}:\s*(.+)', content, re.MULTILINE)
    if m:
        val = m.group(1).strip().strip('"').strip("'")
        try:
            return float(val)
        except ValueError:
            return val
    return None

def extract_behavior(content):
    """Extract behavior section numeric values."""
    fields = ['risk_tolerance', 'detail_orientation', 'speed_vs_quality',
              'autonomy_preference', 'communication_density']
    result = {}
    for f in fields:
        val = extract_field(content, f)
        if val is not None:
            try:
                result[f] = float(val)
            except (ValueError, TypeError):
                pass
    return result

def extract_domains(content):
    """Extract knowledge.domains as list of dicts."""
    domains = []
    in_domains = False
    current = None
    for line in content.split('\n'):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip()) if stripped else -1

        if stripped == 'domains:' or stripped.endswith('domains:'):
            if 'domain_success' in stripped:
                continue
            in_domains = True
            continue

        if in_domains:
            # Left domains section (indent <= 4 and non-empty, non-list-item at domain level)
            if indent >= 0 and indent <= 4 and not stripped.startswith('-'):
                if current:
                    domains.append(current)
                in_domains = False
                continue

            if stripped.startswith('- name:'):
                if current:
                    domains.append(current)
                current = {'name': stripped.split(':', 1)[1].strip()}
            elif current:
                if stripped.startswith('proficiency:'):
                    try:
                        current['proficiency'] = float(stripped.split(':', 1)[1].strip())
                    except ValueError:
                        pass
                elif stripped.startswith('task_count:'):
                    try:
                        current['task_count'] = int(stripped.split(':', 1)[1].strip())
                    except ValueError:
                        pass

    if in_domains and current and current not in domains:
        domains.append(current)
    return domains

def extract_list_field(content, field_name):
    """Extract a YAML list field (inline [] or block -)."""
    m = re.search(rf'{field_name}:\s*\[\s*\]', content)
    if m:
        return []
    m = re.search(rf'{field_name}:\s*\[([^\]]+)\]', content)
    if m:
        items = [i.strip().strip('"').strip("'") for i in m.group(1).split(',')]
        return [i for i in items if i]
    items = []
    in_list = False
    for line in content.split('\n'):
        stripped = line.strip()
        if f'{field_name}:' in stripped:
            in_list = True
            continue
        if in_list:
            if stripped.startswith('- '):
                items.append(stripped[2:].strip().strip('"').strip("'"))
            elif stripped and not stripped.startswith('-'):
                break
    return items

def extract_identity_field(content, field):
    """Extract a field from the identity section."""
    m = re.search(rf'^\s+{field}:\s*"?([^"\n]+)"?', content, re.MULTILINE)
    return m.group(1).strip() if m else None

# Read both files
with open(pa_file) as f:
    content_a = f.read()
with open(pb_file) as f:
    content_b = f.read()

# Identity (combine names)
name_a = extract_identity_field(content_a, 'name') or pa_name
name_b = extract_identity_field(content_b, 'name') or pb_name
speech_a = extract_identity_field(content_a, 'speech_style') or ''
speech_b = extract_identity_field(content_b, 'speech_style') or ''

# Behavior: weighted average
beh_a = extract_behavior(content_a)
beh_b = extract_behavior(content_b)
behavior_fields = ['risk_tolerance', 'detail_orientation', 'speed_vs_quality',
                   'autonomy_preference', 'communication_density']
merged_beh = {}
for key in behavior_fields:
    va = beh_a.get(key, 0.5)
    vb = beh_b.get(key, 0.5)
    merged_beh[key] = round(va * weight_a + vb * weight_b, 2)

# Domains: union with weighted proficiency for shared domains
domains_a = extract_domains(content_a)
domains_b = extract_domains(content_b)
domain_map = {}
for d in domains_a:
    domain_map[d['name']] = d.get('proficiency', 0.0)
merged_domains = []
seen = set()
for d in domains_a:
    name = d['name']
    seen.add(name)
    prof_a = d.get('proficiency', 0.0)
    # Check if also in B
    prof_b = None
    for db in domains_b:
        if db['name'] == name:
            prof_b = db.get('proficiency', 0.0)
            break
    if prof_b is not None:
        merged_prof = round(prof_a * weight_a + prof_b * weight_b, 2)
    else:
        merged_prof = prof_a
    merged_domains.append({'name': name, 'proficiency': merged_prof})
for d in domains_b:
    if d['name'] not in seen:
        merged_domains.append({'name': d['name'], 'proficiency': d.get('proficiency', 0.0)})

# Few-shot refs: union
refs_a = extract_list_field(content_a, 'few_shot_refs')
refs_b = extract_list_field(content_b, 'few_shot_refs')
merged_refs = sorted(set(refs_a + refs_b))

# base_model (take from A)
base_model = extract_field(content_a, 'base_model') or 'claude-sonnet-4-6'
if not isinstance(base_model, str):
    base_model = 'claude-sonnet-4-6'

# Generate YAML
now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
today = datetime.now().strftime('%Y-%m-%d')

domains_yaml = ''
for d in merged_domains:
    domains_yaml += f'      - name: {d["name"]}\n'
    domains_yaml += f'        proficiency: {d["proficiency"]}\n'
    domains_yaml += f'        task_count: 0\n'
    domains_yaml += f'        last_updated: "{today}"\n'

refs_yaml = '[]'
if merged_refs:
    refs_yaml = '\n'
    for ref in merged_refs:
        refs_yaml += f'      - "{ref}"\n'
    refs_yaml = refs_yaml.rstrip('\n')

# Combine speech styles
if speech_a and speech_b and speech_a != speech_b:
    merged_speech = f'{speech_a}・{speech_b}'
elif speech_a:
    merged_speech = speech_a
else:
    merged_speech = speech_b or '冷静'

output = f'''# TANEBI Persona — {new_name} (merged from {pa_name} + {pb_name})
# granularity: portable
persona:
  id: "{new_name}"
  base_model: "{base_model}"
  version: 1
  created_at: "{now}"
  parent_version: null
  lineage: ["{pa_name}", "{pb_name}"]

  identity:
    name: "{name_a} x {name_b}"
    speech_style: "{merged_speech}"
    archetype: hybrid
    origin: merged

  knowledge:
    domains:
{domains_yaml}    few_shot_refs: {refs_yaml}
    anti_patterns: []

  behavior:
    risk_tolerance: {merged_beh['risk_tolerance']}
    detail_orientation: {merged_beh['detail_orientation']}
    speed_vs_quality: {merged_beh['speed_vs_quality']}
    autonomy_preference: {merged_beh['autonomy_preference']}
    communication_density: {merged_beh['communication_density']}
'''

with open(dst_file, 'w') as f:
    f.write(output)

print(f"Merged {pa_name} + {pb_name} -> {new_name} (weight_a={weight_a})")
print(f"  Behavior: weighted average (a={weight_a}, b={weight_b})")
print(f"  Domains: {len(merged_domains)} (union)")
print(f"  Target: {dst_file}")
PYEOF
    ;;

# ============================================================
# snapshot — Save to history
# ============================================================
snapshot)
    [ $# -lt 1 ] && { echo "Error: Usage: persona_ops.sh snapshot <persona>" >&2; exit 1; }
    PERSONA="$1"
    SRC_FILE="$ACTIVE_DIR/${PERSONA}.yaml"
    [ ! -f "$SRC_FILE" ] && { echo "Error: Persona not found: $SRC_FILE" >&2; exit 1; }

    mkdir -p "$HISTORY_DIR"

    # Count existing snapshots to determine gen number
    EXISTING=$(find "$HISTORY_DIR" -name "${PERSONA}_gen*.yaml" 2>/dev/null | wc -l | tr -d ' ')
    GEN=$((EXISTING + 1))
    DST_FILE="$HISTORY_DIR/${PERSONA}_gen${GEN}.yaml"

    cp "$SRC_FILE" "$DST_FILE"
    echo "Snapshot saved: ${PERSONA}_gen${GEN}.yaml"
    echo "  Source: $SRC_FILE"
    echo "  Target: $DST_FILE"
    ;;

# ============================================================
# list — Show all active personas
# ============================================================
list)
    echo "Active Personas:"
    echo "--------------------------------------------------------------"
    printf "%-30s  %-12s  %-10s\n" "ID" "Fitness" "Tasks"
    echo "--------------------------------------------------------------"

    for f in "$ACTIVE_DIR"/*.yaml; do
        [ ! -f "$f" ] && continue

        python3 - "$f" <<'PYEOF'
import sys, re

filepath = sys.argv[1]
with open(filepath) as f:
    content = f.read()

# Extract persona id
m = re.search(r'^\s+id:\s*"?([^"\n]+)"?', content, re.MULTILINE)
pid = m.group(1).strip() if m else '???'

# Extract fitness_score (under evolution section)
m = re.search(r'fitness_score:\s*([\d.]+)', content)
fitness = m.group(1) if m else 'N/A'

# Extract total_tasks (under performance section) or sum of task_count in domains
m = re.search(r'total_tasks:\s*(\d+)', content)
if m:
    tasks = m.group(1)
else:
    # Sum domain task_counts
    counts = re.findall(r'task_count:\s*(\d+)', content)
    total = sum(int(c) for c in counts)
    tasks = str(total)

print(f'{pid:<30s}  {fitness:<12s}  {tasks:<10s}')
PYEOF
    done
    ;;

# ============================================================
# restore — Restore from snapshot
# ============================================================
restore)
    [ $# -lt 1 ] && { echo "Error: Usage: persona_ops.sh restore <snapshot_path>" >&2; exit 1; }
    SNAPSHOT="$1"

    # Handle relative paths from history dir
    if [ ! -f "$SNAPSHOT" ] && [ -f "$HISTORY_DIR/$SNAPSHOT" ]; then
        SNAPSHOT="$HISTORY_DIR/$SNAPSHOT"
    fi
    [ ! -f "$SNAPSHOT" ] && { echo "Error: Snapshot not found: $SNAPSHOT" >&2; exit 1; }

    # Extract persona_id from the snapshot
    PERSONA_ID=$(python3 -c "
import sys, re
with open(sys.argv[1]) as f:
    content = f.read()
m = re.search(r'^\s+id:\s*\"?([^\"\n]+)\"?', content, re.MULTILINE)
print(m.group(1).strip() if m else '')
" "$SNAPSHOT")

    [ -z "$PERSONA_ID" ] && { echo "Error: Could not extract persona ID from $SNAPSHOT" >&2; exit 1; }

    DST_FILE="$ACTIVE_DIR/${PERSONA_ID}.yaml"
    cp "$SNAPSHOT" "$DST_FILE"
    echo "Restored: $(basename "$SNAPSHOT") -> ${PERSONA_ID}.yaml"
    echo "  Source: $SNAPSHOT"
    echo "  Target: $DST_FILE"
    ;;

*)
    echo "Error: Unknown command: $CMD" >&2
    usage
    ;;

esac
