#!/usr/bin/env bash
set -euo pipefail

PERSONA_DIR="${HOME}/projects/tanebi/personas/active"

# ─── YAML parsing helpers (pure bash/awk, no PyYAML) ───

# Extract scalar value: yaml_val <file> <section> <key>
#   section="ROOT" → 2-space indent fields under persona:
#   otherwise      → 4-space indent fields within named section
yaml_val() {
    local file="$1" section="$2" key="$3"
    if [[ "$section" == "ROOT" ]]; then
        awk -v key="$key" '
            BEGIN { pat = "^  " key ":" }
            $0 ~ pat {
                v=$0; sub(/.*: */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
                print v; exit
            }' "$file"
    else
        awk -v sec="$section" -v key="$key" '
            BEGIN { ps="^  " sec ":"; pk="^    " key ":"; ins=0 }
            $0 ~ ps { ins=1; next }
            ins && /^  [a-zA-Z_]/ { ins=0 }
            ins && $0 ~ pk {
                v=$0; sub(/.*: */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
                print v; exit
            }' "$file"
    fi
}

# First domain in knowledge.domains
top_domain() {
    awk '
        BEGIN { ik=0; id=0 }
        /^  knowledge:/ { ik=1; next }
        ik && /^  [a-zA-Z_]+:/ { ik=0; next }
        ik && /^    domains:/ { id=1; next }
        id && /^    [^ -]/ { id=0; next }
        id && /- name:/ {
            v=$0; sub(/.*: */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
            print v; exit
        }' "$1"
}

# All domain names (comma-separated)
all_domains() {
    awk '
        BEGIN { ik=0; id=0; first=1 }
        /^  knowledge:/ { ik=1; next }
        ik && /^  [a-zA-Z_]+:/ { ik=0; next }
        ik && /^    domains:/ { id=1; next }
        id && /^    [^ -]/ { id=0; next }
        id && /- name:/ {
            v=$0; sub(/.*: */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
            if (!first) printf ", "
            printf "%s", v; first=0
        }
        END { print "" }' "$1"
}

# Anti-patterns list
get_anti_patterns() {
    awk '
        BEGIN { ik=0; ia=0; first=1 }
        /^  knowledge:/ { ik=1; next }
        ik && /^  [a-zA-Z_]+:/ { ik=0; next }
        ik && /^    anti_patterns:/ {
            if ($0 ~ /\[\]/) { print "[]"; first=0; exit }
            ia=1; next
        }
        ia && (/^    [a-zA-Z_]+:/ || /^  [a-zA-Z_]+:/) { ia=0; next }
        ia && /^ *- / {
            v=$0; sub(/^ *- */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
            if (!first) printf ", "
            printf "%s", v; first=0
        }
        END { if (first) print "[]"; else print "" }' "$1"
}

# Strengths list (may not exist in all personas)
get_strengths() {
    awk '
        BEGIN { is=0; first=1 }
        /^    strengths:/ {
            if ($0 ~ /\[\]/) { print "[]"; first=0; exit }
            is=1; next
        }
        is && (/^    [a-zA-Z_]+:/ || /^  [a-zA-Z_]+:/) { is=0; next }
        is && /^ *- / {
            v=$0; sub(/^ *- */, "", v); gsub(/"/, "", v); sub(/ *$/, "", v)
            if (!first) printf ", "
            printf "%s", v; first=0
        }
        END { if (first) print "[]"; else print "" }' "$1"
}

# Format rate as percent: 1.0→100%, 0.92→92%
fmt_pct() {
    [[ -z "$1" ]] && { echo "N/A"; return; }
    awk -v v="$1" 'BEGIN { printf "%.0f%%\n", v * 100 }'
}

# Format fitness to 3 decimal places
fmt_fitness() {
    [[ -z "$1" ]] && { echo "N/A"; return; }
    awk -v v="$1" 'BEGIN { printf "%.3f\n", v }'
}

# ─── Table mode (default) ───

show_table() {
    local files=("$PERSONA_DIR"/*.yaml)
    [[ ! -e "${files[0]}" ]] && { echo "No personas found in $PERSONA_DIR"; return 0; }

    echo ""
    echo "=== TANEBI Persona Evolution Status ==="
    {
        printf "ID\tNAME\tFITNESS\tTRUST\tTASKS\tSUCCESS%%\tTOP_DOMAIN\n"
        for f in "${files[@]}"; do
            local p_id p_name fitness trust tasks success top
            p_id=$(yaml_val "$f" ROOT id)
            p_name=$(yaml_val "$f" identity name)
            fitness=$(yaml_val "$f" evolution fitness_score)
            trust=$(yaml_val "$f" performance trust_score)
            tasks=$(yaml_val "$f" performance total_tasks)
            [[ -z "$tasks" ]] && tasks=$(yaml_val "$f" performance tasks_completed)
            success=$(yaml_val "$f" performance success_rate)
            top=$(top_domain "$f")

            fitness=$(fmt_fitness "$fitness")
            [[ -z "$trust" ]] && trust="N/A"
            [[ -z "$tasks" ]] && tasks="0"
            success=$(fmt_pct "$success")
            [[ -z "$top" ]] && top="general"

            printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\n" \
                "$p_id" "$p_name" "$fitness" "$trust" "$tasks" "$success" "$top"
        done
    } | if command -v column &>/dev/null; then
        column -t -s $'\t'
    else
        cat
    fi
    echo ""
}

# ─── JSON mode ───

show_json() {
    local files=("$PERSONA_DIR"/*.yaml)
    [[ ! -e "${files[0]}" ]] && { echo "[]"; return 0; }

    echo "["
    local first=true
    for f in "${files[@]}"; do
        local p_id p_name fitness trust tasks success top
        p_id=$(yaml_val "$f" ROOT id)
        p_name=$(yaml_val "$f" identity name)
        fitness=$(yaml_val "$f" evolution fitness_score)
        trust=$(yaml_val "$f" performance trust_score)
        tasks=$(yaml_val "$f" performance total_tasks)
        [[ -z "$tasks" ]] && tasks=$(yaml_val "$f" performance tasks_completed)
        success=$(yaml_val "$f" performance success_rate)
        top=$(top_domain "$f")

        [[ -z "$fitness" ]] && fitness="null"
        [[ -z "$trust" ]] && trust="null"
        [[ -z "$tasks" ]] && tasks="0"
        [[ -z "$success" ]] && success="null"
        [[ -z "$top" ]] && top="general"

        $first || printf ",\n"
        printf '  {"id":"%s","name":"%s","fitness":%s,"trust":%s,"tasks":%s,"success_rate":%s,"top_domain":"%s"}' \
            "$p_id" "$p_name" "$fitness" "$trust" "$tasks" "$success" "$top"
        first=false
    done
    echo ""
    echo "]"
}

# ─── Detail mode ───

show_detail() {
    local target="$1" found=false

    for f in "$PERSONA_DIR"/*.yaml; do
        [[ ! -e "$f" ]] && continue
        local p_id
        p_id=$(yaml_val "$f" ROOT id)
        [[ "$p_id" != "$target" ]] && continue

        found=true
        local p_name fitness trust tasks success domains strengths apatterns last_updated
        p_name=$(yaml_val "$f" identity name)
        fitness=$(yaml_val "$f" evolution fitness_score)
        trust=$(yaml_val "$f" performance trust_score)
        tasks=$(yaml_val "$f" performance total_tasks)
        [[ -z "$tasks" ]] && tasks=$(yaml_val "$f" performance tasks_completed)
        success=$(yaml_val "$f" performance success_rate)
        domains=$(all_domains "$f")
        strengths=$(get_strengths "$f")
        apatterns=$(get_anti_patterns "$f")
        last_updated=$(yaml_val "$f" evolution last_updated)

        fitness=$(fmt_fitness "$fitness")
        [[ -z "$trust" ]] && trust="N/A"
        [[ -z "$tasks" ]] && tasks="0"
        success=$(fmt_pct "$success")
        [[ -z "$domains" ]] && domains="general"
        [[ -z "$last_updated" ]] && last_updated="N/A"

        echo ""
        echo "=== ${target} 詳細 ==="
        echo "name: $p_name"
        echo "fitness_score: $fitness"
        echo "trust_score: $trust"
        echo "tasks_completed: $tasks"
        echo "success_rate: $success"
        echo "domains: [$domains]"
        echo "strengths: $strengths"
        echo "anti_patterns: $apatterns"
        echo "last_updated: $last_updated"
        echo ""
        break
    done

    $found || { echo "Error: persona '${target}' not found in $PERSONA_DIR" >&2; exit 1; }
}

# ─── Usage ───

usage() {
    cat <<'HELP'
Usage: show_evolution.sh [OPTIONS]

Options:
  (none)               Table view of all personas
  --json               JSON output
  --detail <id>        Detailed view of a specific persona
  -h, --help           Show this help
HELP
}

# ─── Entry point ───

case "${1:-}" in
    --json)     show_json ;;
    --detail)
        [[ -z "${2:-}" ]] && { echo "Error: --detail requires persona_id" >&2; usage >&2; exit 1; }
        show_detail "$2" ;;
    -h|--help)  usage ;;
    "")         show_table ;;
    *)          echo "Error: unknown option '$1'" >&2; usage >&2; exit 1 ;;
esac
