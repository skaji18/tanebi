#!/usr/bin/env python3
"""TANEBI evolution helper: updates Persona YAMLs based on Worker results."""

import sys
import os
import glob
import re
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
            fm[key.strip()] = val.strip()
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

def evolve(results_dir, personas_dir, cmd_id):
    today = date.today().isoformat()
    now = datetime.now().isoformat()

    # Collect results
    results = []
    for path in glob.glob(os.path.join(results_dir, '*.md')):
        with open(path) as f:
            content = f.read()
        fm = parse_frontmatter(content)
        if fm:
            results.append(fm)
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
            persona_stats[persona] = {'total': 0, 'success': 0, 'domains': {}}
        persona_stats[persona]['total'] += 1
        if r.get('status') == 'success':
            persona_stats[persona]['success'] += 1
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

    # Log GREEN quality results as Few-Shot candidates
    green_results = [r for r in results if r.get('quality') == 'GREEN' and r.get('status') == 'success']
    if green_results:
        print(f"  [evolve] {len(green_results)} GREEN result(s) are Few-Shot candidates:")
        for r in green_results:
            print(f"    - {r.get('subtask_id', '?')} (domain: {r.get('domain','?')}, persona: {r.get('persona','?')})")
        print("  [evolve] Manual registration to few_shot_bank recommended.")

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: _evolve_helper.py <results_dir> <personas_dir> <cmd_id>", file=sys.stderr)
        sys.exit(1)
    evolve(sys.argv[1], sys.argv[2], sys.argv[3])
