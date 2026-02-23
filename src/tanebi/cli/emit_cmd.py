"""tanebi emit CLI サブコマンド — サブエージェント(Executor)がイベントを発火するための公開API"""
from __future__ import annotations

import argparse
import sys


def add_emit_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi emit <task_id> <event_type> [key=value ...]"""
    emit_p = subparsers.add_parser(
        "emit",
        help="Emit an event to the Event Store",
        description=(
            "Emit an event for a task. Used by Executor subagents to fire "
            "*.completed events.\n\n"
            "Example:\n"
            "  tanebi emit cmd_001 worker.completed "
            "cmd_id=cmd_001 subtask_id=sub_001 "
            "status=success quality=GREEN domain=backend"
        ),
    )
    emit_p.add_argument("task_id", help="Task ID (e.g. cmd_001)")
    emit_p.add_argument("event_type", help="Event type (e.g. worker.completed)")
    emit_p.add_argument(
        "payload",
        nargs="*",
        help="Payload as key=value pairs",
    )
    emit_p.set_defaults(func=_emit)


def _emit(args: argparse.Namespace) -> None:
    from tanebi.core.callback import handle_callback, parse_callback_args

    kwargs = parse_callback_args(args.payload or [])
    kwargs["event_type"] = args.event_type

    try:
        event_path = handle_callback(args.task_id, None, kwargs)
        print(f"[emit] {args.event_type} → {event_path.name}")
    except FileNotFoundError:
        print(f"Error: task '{args.task_id}' not found", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
