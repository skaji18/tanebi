"""tanebi listener / tanebi new CLI サブコマンド"""
from __future__ import annotations
import argparse
from pathlib import Path
import yaml
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class _EventHandler(FileSystemEventHandler):
    """watchdog FileSystemEventHandler — Core + Executor の両方に振り分け"""

    def __init__(self, core_listener, executor_listener):
        self.core = core_listener
        self.executor = executor_listener

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        # work/{task_id}/events/ 以下のファイルだけ処理
        parts = path.parts
        # ... "events" がパスに含まれるか確認
        if "events" not in parts:
            return
        self.core.on_created(path)
        self.executor.on_created(path)


class EventRouter:
    """1つの watchdog Observer で CoreListener + ExecutorListener に振り分け"""

    def __init__(self, tanebi_root: Path):
        self.tanebi_root = tanebi_root

    def start(self) -> None:
        from tanebi.core.listener import CoreListener
        from tanebi.executor.listener import ExecutorListener

        core = CoreListener(self.tanebi_root)
        executor = ExecutorListener(self.tanebi_root)

        handler = _EventHandler(core, executor)
        observer = Observer()
        work_dir = self.tanebi_root / "work"
        work_dir.mkdir(exist_ok=True)
        observer.schedule(handler, str(work_dir), recursive=True)
        observer.start()
        print(f"TANEBI Listener started. Watching: {work_dir}")
        try:
            import time
            while observer.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()


def add_listener_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi listener <subcommand>"""
    listener_parser = subparsers.add_parser("listener", help="Listener 管理")
    listener_sub = listener_parser.add_subparsers(dest="listener_cmd")
    start_p = listener_sub.add_parser("start", help="Listener を起動する")
    start_p.set_defaults(func=_listener_start)


def add_new_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi new <request>"""
    new_p = subparsers.add_parser("new", help="新しいタスクを投入する")
    new_p.add_argument("request", nargs="+", help="タスク依頼テキスト")
    new_p.set_defaults(func=_new_task)


def _listener_start(args: argparse.Namespace) -> None:
    tanebi_root = Path.cwd()
    router = EventRouter(tanebi_root)
    router.start()


def _new_task(args: argparse.Namespace) -> None:
    from tanebi.api import submit
    request = " ".join(args.request)
    task_id = submit(request)
    print(f"Task submitted: {task_id}")
