#!/usr/bin/env python3
"""TANEBI fitness function: calculates and updates agent fitness scores.

Fitness = w1 * quality_score + w2 * completion_rate + w3 * efficiency + w4 * growth_rate

Uses a sliding window of the last N tasks (default 20).
Weights and window size are read from config.yaml.
"""

import os
import sys
import glob
import re
from datetime import date

# Default weights (overridden by config.yaml if available)
DEFAULT_WEIGHTS = {
    'quality_score': 0.35,
    'completion_rate': 0.30,
    'efficiency': 0.20,
    'growth_rate': 0.15,
}
DEFAULT_WINDOW = 20

QUALITY_MAP = {
    'GREEN': 1.0,
    'YELLOW': 0.5,
    'RED': 0.0,
}

DURATION_SCORE = {
    'short': 1.0,
    'medium': 0.7,
    'long': 0.4,
}


def _parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content."""
    lines = content.split('\n')
    if not lines or lines[0].strip() != '---':
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


def _load_persona_identifiers(persona_yaml_path):
    """Extract persona id and name from YAML file."""
    with open(persona_yaml_path) as f:
        content = f.read()
    pid = ''
    name = ''
    m = re.search(r'^\s*id:\s*"?([^"\n]+)"?', content, re.MULTILINE)
    if m:
        pid = m.group(1).strip()
    m = re.search(r'^\s*name:\s*"?([^"\n]+)"?', content, re.MULTILINE)
    if m:
        name = m.group(1).strip()
    return pid, name


def _load_config(tanebi_root):
    """Load fitness config from config.yaml."""
    config_path = os.path.join(tanebi_root, 'config.yaml')
    weights = dict(DEFAULT_WEIGHTS)
    window = DEFAULT_WINDOW
    try:
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        evo = cfg.get('tanebi', {}).get('evolution', {})
        fw = evo.get('fitness_weights', {})
        if fw:
            weights.update(fw)
        window = evo.get('fitness_window', DEFAULT_WINDOW)
    except (ImportError, IOError, OSError):
        pass
    return weights, window


def collect_task_history(work_dir, persona_id, persona_name=''):
    """Collect task results for a persona from work/ directories.

    Matches results by persona id or persona name (identity.name).
    Returns list of dicts sorted by file modification time (oldest first).
    """
    identifiers = {persona_id}
    if persona_name:
        identifiers.add(persona_name)

    results = []
    for result_path in glob.glob(os.path.join(work_dir, 'cmd_*/results/*.md')):
        try:
            with open(result_path) as f:
                content = f.read()
        except (IOError, OSError):
            continue

        fm = _parse_frontmatter(content)
        if not fm:
            continue

        persona_field = fm.get('persona', '')
        if persona_field not in identifiers:
            continue

        results.append({
            'status': fm.get('status', ''),
            'quality': fm.get('quality', ''),
            'domain': fm.get('domain', ''),
            'duration_estimate': fm.get('duration_estimate', ''),
            'mtime': os.path.getmtime(result_path),
        })

    results.sort(key=lambda r: r['mtime'])
    return results


def calculate_fitness(persona_data, task_history=None, weights=None, window=None):
    """Calculate fitness score from persona data and task history.

    Args:
        persona_data: Dict with persona fields (knowledge.domains etc.)
        task_history: List of task result dicts from collect_task_history().
                      If None or empty, returns a base fitness from proficiency.
        weights: Fitness weight dict. Uses DEFAULT_WEIGHTS if None.
        window: Sliding window size. Uses DEFAULT_WINDOW if None.

    Returns:
        float: Fitness score between 0.0 and 1.0
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if window is None:
        window = DEFAULT_WINDOW

    if not task_history:
        # No history: derive base fitness from average proficiency
        domains = persona_data.get('knowledge', {}).get('domains', [])
        if domains:
            avg_prof = sum(d.get('proficiency', 0.5) for d in domains) / len(domains)
            return round(avg_prof * 0.5, 4)
        return 0.25

    recent = task_history[-window:]
    total = len(recent)

    # 1. quality_score: average quality (GREEN=1.0, YELLOW=0.5, RED=0.0)
    quality_values = [QUALITY_MAP.get(r['quality'], 0.5) for r in recent]
    quality_score = sum(quality_values) / total

    # 2. completion_rate: success / total
    successes = sum(1 for r in recent if r['status'] == 'success')
    completion_rate = successes / total

    # 3. efficiency: normalized from duration_estimate (short=1.0, medium=0.7, long=0.4)
    eff_values = [DURATION_SCORE.get(r.get('duration_estimate', ''), 0.5) for r in recent]
    efficiency = sum(eff_values) / total

    # 4. growth_rate: compare first-half vs second-half quality improvement
    #    Normalized to 0.0-1.0 (0.5 = no change)
    if total >= 4:
        half = total // 2
        first_q = sum(QUALITY_MAP.get(r['quality'], 0.5) for r in recent[:half]) / half
        second_q = sum(QUALITY_MAP.get(r['quality'], 0.5) for r in recent[half:]) / (total - half)
        growth_rate = min(max((second_q - first_q + 1.0) / 2.0, 0.0), 1.0)
    else:
        growth_rate = 0.5

    fitness = (
        weights.get('quality_score', 0.35) * quality_score
        + weights.get('completion_rate', 0.30) * completion_rate
        + weights.get('efficiency', 0.20) * efficiency
        + weights.get('growth_rate', 0.15) * growth_rate
    )

    return round(min(max(fitness, 0.0), 1.0), 4)


def update_fitness_score(persona_yaml_path):
    """Update evolution.fitness_score in a Persona YAML and return the score.

    Reads task history from work/, calculates fitness, writes back to YAML.

    Args:
        persona_yaml_path: Absolute or relative path to a persona YAML file.

    Returns:
        float: The calculated fitness score.
    """
    persona_yaml_path = os.path.expanduser(persona_yaml_path)

    # Derive tanebi root: .../tanebi/personas/active/xxx.yaml → .../tanebi
    tanebi_root = os.path.dirname(os.path.dirname(os.path.dirname(persona_yaml_path)))

    weights, window = _load_config(tanebi_root)

    # Load persona identifiers
    persona_id, persona_name = _load_persona_identifiers(persona_yaml_path)

    # Build persona_data for calculate_fitness
    persona_data = {}
    try:
        import yaml
        with open(persona_yaml_path) as f:
            raw = yaml.safe_load(f)
        persona_data = raw.get('persona', raw) if isinstance(raw, dict) else {}
    except (ImportError, IOError):
        pass

    # Collect history & calculate
    work_dir = os.path.join(tanebi_root, 'work')
    task_history = collect_task_history(work_dir, persona_id, persona_name)
    fitness = calculate_fitness(persona_data, task_history, weights, window)

    # Update YAML file
    with open(persona_yaml_path) as f:
        content = f.read()

    today = date.today().isoformat()

    if 'evolution:' in content:
        if 'fitness_score:' in content:
            content = re.sub(
                r'(fitness_score:\s*)[\d.]+',
                rf'\g<1>{fitness}',
                content, count=1,
            )
        else:
            content = content.replace(
                'evolution:',
                f'evolution:\n    fitness_score: {fitness}',
                1,
            )
        # Update or add last_updated within evolution section
        if re.search(r'evolution:.*?last_updated:', content, re.DOTALL):
            content = re.sub(
                r'(evolution:.*?last_updated:\s*)"[^"]*"',
                rf'\g<1>"{today}"',
                content, count=1, flags=re.DOTALL,
            )
        else:
            content = content.replace(
                'evolution:',
                f'evolution:\n    last_updated: "{today}"',
                1,
            )
    else:
        # Append evolution section (indented under persona:)
        content = content.rstrip('\n') + f"""

  evolution:
    fitness_score: {fitness}
    last_updated: "{today}"
"""

    with open(persona_yaml_path, 'w') as f:
        f.write(content)

    print(f"  [fitness] {persona_id}: fitness_score = {fitness} "
          f"(tasks={len(task_history)}, window={window})")
    return fitness


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: _fitness.py <persona_yaml_path> [persona_yaml_path ...]",
              file=sys.stderr)
        print("  Updates evolution.fitness_score for each persona.", file=sys.stderr)
        sys.exit(1)
    for path in sys.argv[1:]:
        update_fitness_score(path)
