"""TANEBI Inbound Callback API — Worker→TANEBI の固定 API。

tanebi-callback.sh の処理を Python で置換する。
"""

from pathlib import Path
from typing import Optional

from tanebi.event_store import emit_event

__all__ = ["handle_callback", "resolve_cmd_dir", "parse_callback_args"]


def parse_callback_args(args: list[str]) -> dict:
    """"key=value" 形式の引数リストを dict に変換する。

    例:
        ["event_type=worker.completed", "status=GREEN"]
        → {"event_type": "worker.completed", "status": "GREEN"}
    """
    result = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            result[key] = value
    return result


def resolve_cmd_dir(cmd_id: str, work_dir: Path) -> Path:
    """cmd_id から CMD_DIR を解決する。存在しない場合は FileNotFoundError。"""
    cmd_dir = Path(work_dir) / cmd_id
    if not cmd_dir.exists():
        raise FileNotFoundError(f"CMD_DIR not found: {cmd_dir}")
    return cmd_dir


def handle_callback(
    cmd_id: str,
    work_dir: Optional[Path],
    kwargs: dict,
) -> Path:
    """Workerからのコールバックを処理する。

    1. cmd_id から CMD_DIR を解決 (work_dir/cmd_id/)
    2. kwargs から event_type を取得（必須）
    3. 残りの kwargs をペイロードとして構築
    4. event_store.emit_event() を呼び出し
    5. 作成されたイベントファイルの Path を返す

    Args:
        cmd_id: タスクID（例: "cmd_042"）
        work_dir: work/ ディレクトリの Path。None の場合は config から自動解決。
        kwargs: key=value 形式の引数 dict
            必須: event_type
            その他: ペイロードに含める任意フィールド

    Returns:
        作成されたイベントファイルの Path
    """
    if work_dir is None:
        from tanebi.core.config import WORK_DIR
        work_dir = Path(WORK_DIR)

    cmd_dir = resolve_cmd_dir(cmd_id, work_dir)

    if "event_type" not in kwargs:
        raise ValueError("event_type is required in kwargs")

    event_type = kwargs["event_type"]
    payload = {k: v for k, v in kwargs.items() if k != "event_type"}

    return emit_event(cmd_dir, event_type, payload, validate=True)
