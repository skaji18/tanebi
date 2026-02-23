"""tanebi persona CLI サブコマンド"""
from __future__ import annotations

import argparse
import sys


def add_persona_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi persona <subcommand>"""
    persona_parser = subparsers.add_parser("persona", help="ペルソナ管理")
    persona_sub = persona_parser.add_subparsers(dest="persona_cmd")
    # persona のみ指定時はヘルプ表示
    persona_parser.set_defaults(func=lambda args: persona_parser.print_help())

    # persona list
    list_p = persona_sub.add_parser("list", help="ペルソナ一覧を表示する")
    list_p.set_defaults(func=_persona_list)

    # persona copy <src> <dst>
    copy_p = persona_sub.add_parser("copy", help="ペルソナをコピーする")
    copy_p.add_argument("src", help="コピー元のペルソナID")
    copy_p.add_argument("dst", help="コピー先のペルソナID")
    copy_p.set_defaults(func=_persona_copy)

    # persona merge <base> <donor> [--output <out>]
    merge_p = persona_sub.add_parser("merge", help="2つのペルソナをマージする")
    merge_p.add_argument("base", help="ベースペルソナID")
    merge_p.add_argument("donor", help="ドナーペルソナID")
    merge_p.add_argument("--output", help="出力ペルソナID（省略時は {base}_x_{donor}）")
    merge_p.set_defaults(func=_persona_merge)


def _persona_list(args: argparse.Namespace) -> None:
    from tanebi.core.persona_ops import list_personas
    try:
        personas = list_personas()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not personas:
        print("(no personas)")
        return

    header = f"{'ID':<20} {'Name':<20} {'Archetype':<15} {'Fitness':>8} {'Tasks':>6}"
    print(header)
    print("-" * len(header))
    for p in personas:
        fitness = p.get("fitness_score")
        fitness_str = f"{fitness:.3f}" if fitness is not None else "N/A"
        tasks = p.get("total_tasks", 0)
        print(f"{p['id']:<20} {p.get('name', ''):<20} {p.get('archetype', ''):<15} {fitness_str:>8} {tasks:>6}")


def _persona_copy(args: argparse.Namespace) -> None:
    from tanebi.core.persona_ops import copy_persona
    try:
        dst_path = copy_persona(args.src, args.dst)
        print(f"Copied: {args.src} → {dst_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _persona_merge(args: argparse.Namespace) -> None:
    from tanebi.core.persona_ops import merge_personas
    output_id = args.output if args.output else f"{args.base}_x_{args.donor}"
    try:
        dst_path = merge_personas(args.base, args.donor, output_id)
        print(f"Merged: {args.base} + {args.donor} → {dst_path}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
