"""tanebi CLI entrypoint."""
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tanebi",
        description="Task-Native Evolution Boost Infrastructure",
    )
    parser.add_argument("--version", action="version", version="tanebi 0.1.0")
    subparsers = parser.add_subparsers(dest="command")
    # TODO: subcommands will be added in Phase 5
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()


if __name__ == "__main__":
    main()
