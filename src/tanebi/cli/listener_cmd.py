"""tanebi listener / tanebi new CLI サブコマンド"""
from __future__ import annotations
import argparse
import signal
import time
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
        self.executor_listener = None
        self._observer = None

    def start(self) -> None:
        from tanebi.core.listener import CoreListener
        from tanebi.executor.listener import ExecutorListener

        core = CoreListener(self.tanebi_root)
        self.executor_listener = ExecutorListener(self.tanebi_root)

        handler = _EventHandler(core, self.executor_listener)
        self._observer = Observer()
        work_dir = self.tanebi_root / "work"
        work_dir.mkdir(exist_ok=True)
        self._observer.schedule(handler, str(work_dir), recursive=True)
        self._observer.start()
        print(f"TANEBI Listener started. Watching: {work_dir}")

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()


def add_listener_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi listener <subcommand>"""
    listener_parser = subparsers.add_parser("listener", help="Manage listener")
    listener_sub = listener_parser.add_subparsers(dest="listener_cmd")
    start_p = listener_sub.add_parser("start", help="Start the listener")
    start_p.set_defaults(func=_listener_start)


def add_new_parser(subparsers: argparse._SubParsersAction) -> None:
    """tanebi new <request>"""
    new_p = subparsers.add_parser("new", help="Submit a new task")
    new_p.add_argument("request", nargs="+", help="Task request text")
    new_p.set_defaults(func=_new_task)


def _listener_start(args: argparse.Namespace) -> None:
    tanebi_root = Path.cwd()
    router = EventRouter(tanebi_root)
    router.start()

    def _shutdown(signum=None, frame=None):
        router.stop()
        router.executor_listener.shutdown(wait=True)

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        _shutdown()


def _new_task(args: argparse.Namespace) -> None:
    from tanebi.api import submit
    request = " ".join(args.request)
    task_id = submit(request)
    print(f"Task submitted: {task_id}")
