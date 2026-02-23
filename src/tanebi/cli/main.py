"""tanebi CLI entrypoint."""
import argparse
import sys
from tanebi.cli.listener_cmd import add_listener_parser, add_new_parser
from tanebi.cli.persona_cmd import add_persona_parser
from tanebi.cli.evolve_cmd import add_evolve_parser
from tanebi.cli.emit_cmd import add_emit_parser


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tanebi",
        description="Task-Native Evolution Boost Infrastructure",
    )
    parser.add_argument("--version", action="version", version="tanebi 0.1.0")
    subparsers = parser.add_subparsers(dest="command")
    add_listener_parser(subparsers)
    add_new_parser(subparsers)
    add_persona_parser(subparsers)
    add_evolve_parser(subparsers)
    add_emit_parser(subparsers)

    # status [<task_id>]
    status_p = subparsers.add_parser("status", help="Show task status")
    status_p.add_argument("task_id", nargs="?", help="Task ID (defaults to all tasks)")
    status_p.set_defaults(func=_status)

    # config
    config_p = subparsers.add_parser("config", help="Show current config")
    config_p.set_defaults(func=_config)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
    elif hasattr(args, "func"):
        args.func(args)


def _status(args: argparse.Namespace) -> None:
    from pathlib import Path
    from tanebi.event_store import get_task_summary
    from tanebi.config import WORK_DIR

    work_dir = Path(WORK_DIR)

    if args.task_id:
        cmd_dir = work_dir / args.task_id
        if not cmd_dir.exists():
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)
        summary = get_task_summary(cmd_dir)
        print(f"Task:   {summary['task_id']}")
        print(f"State:  {summary['state']}")
        print(f"Events: {summary['event_count']}")
    else:
        if not work_dir.exists():
            print("(no work directory)")
            return
        task_dirs = [d for d in sorted(work_dir.iterdir()) if d.is_dir()]
        if not task_dirs:
            print("(no tasks)")
            return
        for d in task_dirs:
            summary = get_task_summary(d)
            print(f"{summary['task_id']}: {summary['state']} ({summary['event_count']} events)")


def _config(args: argparse.Namespace) -> None:
    import yaml
    from pathlib import Path
    from tanebi.config import TANEBI_ROOT

    config_path = Path(TANEBI_ROOT) / "config.yaml"
    if not config_path.exists():
        print(f"config.yaml not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    def _print_dict(d: dict, indent: int = 0) -> None:
        prefix = "  " * indent
        for k, v in d.items():
            if isinstance(v, dict):
                print(f"{prefix}{k}:")
                _print_dict(v, indent + 1)
            else:
                print(f"{prefix}{k}={v}")

    _print_dict(config)


if __name__ == "__main__":
    main()
