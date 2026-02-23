"""tanebi evolve CLI subcommand.

Usage:
  tanebi evolve <task_id> <persona_id>   — run persona evolution
  tanebi evolve show [<persona_id>]      — show evolution/performance section
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def add_evolve_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register 'tanebi evolve' subcommand."""
    evolve_p = subparsers.add_parser(
        "evolve",
        help="Evolve a persona based on task results",
    )
    # Accept first positional as task_id OR "show" subcommand keyword
    evolve_p.add_argument("task_id", nargs="?", help="Task ID (e.g. cmd_001) or 'show'")
    evolve_p.add_argument("persona_id", nargs="?", help="Persona ID")
    evolve_p.set_defaults(func=_evolve_dispatch)


def _evolve_dispatch(args: argparse.Namespace) -> None:
    """Dispatch to run or show based on first positional argument."""
    if args.task_id == "show":
        _evolve_show(args)
    elif args.task_id and args.persona_id:
        _evolve_run(args)
    else:
        print(
            "Usage:\n"
            "  tanebi evolve <task_id> <persona_id>\n"
            "  tanebi evolve show [<persona_id>]",
            file=sys.stderr,
        )
        sys.exit(1)


def _evolve_run(args: argparse.Namespace) -> None:
    """Run persona evolution for a task."""
    from tanebi.core.evolve import evolve_persona
    from tanebi.core.config import TANEBI_ROOT, PERSONA_DIR

    persona_dir = Path(PERSONA_DIR)
    persona_path = persona_dir / f"{args.persona_id}.yaml"

    if not persona_path.exists():
        print(f"Persona not found: {persona_path}", file=sys.stderr)
        sys.exit(1)

    report = evolve_persona(
        task_id=args.task_id,
        persona_path=persona_path,
        tanebi_root=Path(TANEBI_ROOT),
    )

    print(f"[evolve] task_id:      {report['task_id']}")
    print(f"[evolve] persona_id:   {report['persona_id']}")
    print(f"[evolve] fitness_score:{report['fitness_score']:.4f}")
    print(f"[evolve] success_rate: {report['success_rate']:.4f}")
    print(f"[evolve] total_tasks:  {report['total_tasks']}")
    print(f"[evolve] few_shot:     {'added' if report['few_shot_added'] else 'not added'}")
    print(f"[evolve] snapshot:     {report['snapshot_path']}")


def _evolve_show(args: argparse.Namespace) -> None:
    """Show evolution/performance section from persona YAML."""
    import yaml
    from tanebi.core.config import PERSONA_DIR
    from tanebi.core.persona_ops import list_personas

    # args.persona_id holds the optional persona_id when dispatched via "show"
    target_id = args.persona_id

    if target_id:
        persona_path = Path(PERSONA_DIR) / f"{target_id}.yaml"
        if not persona_path.exists():
            print(f"Persona not found: {persona_path}", file=sys.stderr)
            sys.exit(1)
        _print_persona_evolution(persona_path)
    else:
        # Show all
        for p in list_personas():
            persona_path = Path(PERSONA_DIR) / f"{p['id']}.yaml"
            if persona_path.exists():
                _print_persona_evolution(persona_path)
                print()


def _print_persona_evolution(persona_path: Path) -> None:
    """Print evolution and performance sections from a persona YAML."""
    import yaml

    with persona_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        return

    persona = data.get("persona", data)
    if not isinstance(persona, dict):
        return

    persona_id = persona.get("id", persona_path.stem)
    print(f"=== {persona_id} ===")

    evolution = persona.get("evolution") or {}
    performance = persona.get("performance") or {}

    print(f"  fitness_score: {evolution.get('fitness_score', 'N/A')}")
    print(f"  last_updated:  {evolution.get('last_updated', 'N/A')}")
    print(f"  total_tasks:   {performance.get('total_tasks', 0)}")
    print(f"  success_count: {performance.get('success_count', 0)}")
    sr = performance.get('success_rate')
    if sr is not None:
        print(f"  success_rate:  {sr:.1%}")
    else:
        print(f"  success_rate:  N/A")
