"""tanebi CLI entrypoint."""
import argparse
from tanebi.cli.listener_cmd import add_listener_parser, add_new_parser


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tanebi",
        description="Task-Native Evolution Boost Infrastructure",
    )
    parser.add_argument("--version", action="version", version="tanebi 0.1.0")
    subparsers = parser.add_subparsers(dest="command")
    add_listener_parser(subparsers)
    add_new_parser(subparsers)
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()


if __name__ == "__main__":
    main()
