#!/usr/bin/env python3
"""TANEBI evolution helper: updates Persona YAMLs based on Worker results."""

import sys
import os
import glob
import re
import shutil
from datetime import datetime, date

def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content."""
    lines = content.split('\n')
    if lines[0].strip() != '---':
        return {}
    end = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            end = i
            break
    if end == -1:
        return {}
    fm = {}
    for line in lines[1:end]:
        if ':' in line:
            key, _, val = line.partition(':')
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm

def load_yaml_simple(path):
    """Simple YAML loader for Persona files (handles basic structure)."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f)
    except ImportError:
        pass
    # Fallback: return raw lines
    with open(path) as f:
        return f.read()

def register_few_shot(fm, content, domain, few_shot_bank_dir, cmd_id):
    """Register a GREEN+success result into the few-shot bank."""
    domain_dir = os.path.join(few_shot_bank_dir, domain)
    os.makedirs(domain_dir, exist_ok=True)

    # Build filename: {cmd_id}_{task_type or subtask_id}.md
    task_type = fm.get('task_type', fm.get('subtask_id', 'task'))
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', task_type)
    filename = f"{cmd_id}_{safe_name}.md"
    filepath = os.path.join(domain_dir, filename)

    # Extract body (everything after frontmatter)
    body = content
    if content.count('---') >= 2:
        parts = content.split('---', 2)
        body = parts[2].strip()

    tags_raw = fm.get('tags', '')
    if tags_raw and not tags_raw.startswith('['):
        tags_raw = f"[{tags_raw}]"
    elif not tags_raw:
        tags_raw = '[]'

    entry = f"""---
domain: {domain}
task_type: {fm.get('task_type', 'general')}
quality: GREEN
persona: {fm.get('persona', 'unknown')}
created_at: "{date.today().isoformat()}"
source_cmd: "{cmd_id}"
tags: {tags_raw}
---

{body}
"""

    with open(filepath, 'w') as f:
        f.write(entry)
    print(f"  [evolve] Registered few-shot: {domain}/{filename}")

    # Enforce max 20 files per domain (delete oldest by mtime)
    entries = sorted(
        glob.glob(os.path.join(domain_dir, '*.md')),
        key=os.path.getmtime
    )
    # Exclude _format.md from deletion
    entries = [e for e in entries if os.path.basename(e) != '_format.md']
    while len(entries) > 20:
        oldest = entries.pop(0)
        os.remove(oldest)
        print(f"  [evolve] Removed oldest few-shot (over 20 limit): {os.path.basename(oldest)}")


def evolve(results_dir, personas_dir, cmd_id):
    today = date.today().isoformat()
    now = datetime.now().isoformat()

    # Derive few_shot_bank_dir from project structure
    tanebi_root = os.path.dirname(os.path.dirname(personas_dir))
    few_shot_bank_dir = os.path.join(tanebi_root, 'knowledge', 'few_shot_bank')

    # Collect results (with content for few-shot registration)
    results = []
    result_contents = {}
    for path in glob.glob(os.path.join(results_dir, '*.md')):
        with open(path) as f:
            content = f.read()
        fm = parse_frontmatter(content)
        if fm:
            results.append(fm)
            result_contents[id(fm)] = content
            print(f"  [evolve] Found result: {os.path.basename(path)} persona={fm.get('persona','?')} status={fm.get('status','?')} quality={fm.get('quality','?')}")

    if not results:
        print("[evolve] No results found to process.")
        return

    # Group by persona
    persona_stats = {}
    for r in results:
        persona = r.get('persona', '')
        if not persona:
            continue
        if persona not in persona_stats:
            persona_stats[persona] = {
                'total': 0, 'success': 0, 'domains': {},
                'failed_domains': [], 'failure_reasons': [],
                'green_count': 0, 'red_count': 0
            }
        persona_stats[persona]['total'] += 1
        if r.get('status') == 'success':
            persona_stats[persona]['success'] += 1
        if r.get('status') == 'failure':
            fail_domain = r.get('domain', '')
            if fail_domain:
                persona_stats[persona]['failed_domains'].append(fail_domain)
            fr = r.get('failure_reason', '')
            if fr:
                persona_stats[persona]['failure_reasons'].append(fr)
        quality = r.get('quality', '')
        if quality == 'GREEN':
            persona_stats[persona]['green_count'] += 1
        elif quality == 'RED':
            persona_stats[persona]['red_count'] += 1
        domain = r.get('domain', '')
        if domain:
            persona_stats[persona]['domains'][domain] = \
                persona_stats[persona]['domains'].get(domain, 0) + 1

    # Update each Persona YAML
    for persona_id, stats in persona_stats.items():
        persona_path = os.path.join(personas_dir, f"{persona_id}.yaml")
        if not os.path.exists(persona_path):
            print(f"  [evolve] WARNING: Persona not found: {persona_path}")
            continue

        with open(persona_path) as f:
            content = f.read()

        # Update performance.total_tasks
        total = stats['total']
        success = stats['success']
        success_rate = round(success / total, 3) if total > 0 else 0.0

        # Simple text-based update (preserves YAML structure)
        # Update or add performance section
        if 'performance:' not in content:
            content += f"""
  performance:
    total_tasks: {total}
    success_rate: {success_rate}
    last_task_date: "{today}"
"""
        else:
            # Increment total_tasks
            def inc_total(m):
                old = int(m.group(1))
                return f"total_tasks: {old + total}"
            content = re.sub(r'total_tasks:\s*(\d+)', inc_total, content)
            content = re.sub(r'success_rate:\s*[\d.]+', f'success_rate: {success_rate}', content)
            content = re.sub(r'last_task_date:\s*"[^"]*"', f'last_task_date: "{today}"', content)

        # Update domain task_counts
        for domain, count in stats['domains'].items():
            def inc_domain(m, c=count):
                old = int(m.group(1))
                return f"task_count: {old + c}"
            # Only update if the domain is already present
            domain_pattern = rf'(name: {re.escape(domain)}.*?task_count:\s*)(\d+)'
            if re.search(domain_pattern, content, re.DOTALL):
                def domain_inc(m, c=count):
                    old = int(m.group(2))
                    return m.group(1) + str(old + c)
                content = re.sub(domain_pattern, domain_inc, content, flags=re.DOTALL)

        # --- Feature 1: Failure correction (proficiency -0.02 per failure) ---
        failed_domain_counts = {}
        for d in stats.get('failed_domains', []):
            failed_domain_counts[d] = failed_domain_counts.get(d, 0) + 1
        for domain, fail_count in failed_domain_counts.items():
            prof_pattern = rf'(name: {re.escape(domain)}.*?proficiency:\s*)([\d.]+)'
            def adjust_prof(m, delta=-0.02 * fail_count):
                old = float(m.group(2))
                new = max(0.0, round(old + delta, 2))
                return m.group(1) + str(new)
            content = re.sub(prof_pattern, adjust_prof, content, count=1, flags=re.DOTALL)
            print(f"  [evolve] Correction: {persona_id} {domain} proficiency -{0.02 * fail_count:.2f}")

        # --- Feature 2: Anti-pattern addition from failure_reason ---
        new_anti_patterns = []
        for reason in stats.get('failure_reasons', []):
            if reason and reason not in content:
                new_anti_patterns.append(reason)
        if new_anti_patterns:
            entries = '\n'.join(f'      - "{r}"' for r in new_anti_patterns)
            if 'anti_patterns: []' in content:
                content = content.replace('anti_patterns: []',
                                          f'anti_patterns:\n{entries}')
            elif 'anti_patterns:' in content:
                ap_match = re.search(r'(anti_patterns:(?:\n      - [^\n]+)*)', content)
                if ap_match:
                    insert_pos = ap_match.end(1)
                    content = content[:insert_pos] + '\n' + entries + content[insert_pos:]
            print(f"  [evolve] Anti-patterns added to {persona_id}: {new_anti_patterns}")

        # --- Feature 3: Behavior adjustment (risk_tolerance based on quality) ---
        net_quality = stats.get('green_count', 0) - stats.get('red_count', 0)
        if net_quality != 0:
            delta = 0.01 * net_quality
            rt_match = re.search(r'(risk_tolerance:\s*)([\d.]+)', content)
            if rt_match:
                old_val = float(rt_match.group(2))
                new_val = max(0.0, min(1.0, round(old_val + delta, 2)))
                content = re.sub(r'(risk_tolerance:\s*)[\d.]+',
                                 f'\\g<1>{new_val}', content)
                print(f"  [evolve] Behavior: {persona_id} risk_tolerance {old_val} -> {new_val}")

        # Add evolution event
        evolution_event = f"""
      - event: "task_completion"
        cmd: "{cmd_id}"
        date: "{today}"
        tasks_processed: {total}
        success_rate: {success_rate}
"""
        if 'evolution:' not in content:
            content += f"""
  evolution:
    last_evolution_event:{evolution_event}"""
        else:
            # Append to last_evolution_event list or add entry
            if 'last_evolution_event:' not in content:
                content = content.replace('evolution:', f'evolution:\n    last_evolution_event:{evolution_event}')

        with open(persona_path, 'w') as f:
            f.write(content)

        print(f"  [evolve] Updated Persona: {persona_id} (tasks: +{total}, success_rate: {success_rate})")

        # Update fitness score
        try:
            from _fitness import update_fitness_score
            update_fitness_score(persona_path)
        except Exception as e:
            print(f"  [evolve] WARNING: fitness update failed for {persona_id}: {e}")

        # --- Feature 4: Auto-snapshot every 5 tasks ---
        total_match = re.search(r'total_tasks:\s*(\d+)', content)
        if total_match:
            current_total = int(total_match.group(1))
            if current_total > 0 and current_total % 5 == 0:
                history_dir = os.path.join(os.path.dirname(personas_dir), 'history')
                os.makedirs(history_dir, exist_ok=True)
                existing = glob.glob(os.path.join(history_dir, f"{persona_id}_gen*.yaml"))
                generation = len(existing) + 1
                snapshot_path = os.path.join(history_dir, f"{persona_id}_gen{generation}.yaml")
                shutil.copy2(persona_path, snapshot_path)
                print(f"  [evolve] Snapshot: {snapshot_path} (total_tasks={current_total})")

    # Auto-register GREEN+success results to few-shot bank
    green_results = [r for r in results if r.get('quality') == 'GREEN' and r.get('status') == 'success']
    if green_results:
        print(f"  [evolve] {len(green_results)} GREEN result(s) — auto-registering to few-shot bank:")
        for r in green_results:
            domain = r.get('domain', 'general')
            content = result_contents.get(id(r), '')
            register_few_shot(r, content, domain, few_shot_bank_dir, cmd_id)

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: _evolve_helper.py <results_dir> <personas_dir> <cmd_id>", file=sys.stderr)
        sys.exit(1)
    evolve(sys.argv[1], sys.argv[2], sys.argv[3])
