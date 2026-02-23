"""TANEBI Event Store — イベント発火・フィードバック管理"""
from __future__ import annotations

import errno
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_schema(schema_path: str | Path | None = None) -> dict:
    """
    events/schema.yaml を読み込んでdictで返す。
    schema_path=None のとき TANEBI_ROOT/events/schema.yaml を自動解決。
    """
    if schema_path is None:
        # src/tanebi/core/event_store.py → tanebi/
        tanebi_root = Path(__file__).parent.parent.parent.parent
        schema_path = tanebi_root / "events" / "schema.yaml"
    schema_path = Path(schema_path)
    with schema_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_payload(event_type: str, payload: dict, schema: dict) -> None:
    """
    schema.yaml に基づきペイロードを検証。
    必須フィールド欠落時は ValueError を送出。
    """
    events = schema.get("events", {})
    if event_type not in events:
        return

    payload_schema = events[event_type].get("payload", {})
    for field_name, field_type in payload_schema.items():
        type_str = str(field_type) if field_type is not None else ""
        # "number?" / "string?" など末尾 "?" = optional
        if type_str.endswith("?"):
            continue
        if field_name not in payload:
            raise ValueError(
                f"イベント '{event_type}' の必須フィールド '{field_name}' が不足しています"
            )


def emit_event(
    cmd_dir: str | Path,
    event_type: str,
    payload: dict,
    validate: bool = True,
) -> Path:
    """
    Event Storeにイベントを発火する。
    cmd_dir/events/ 以下に連番YAMLファイルを書き出す。
    validate=True のとき events/schema.yaml でペイロード検証。
    戻り値: 作成されたイベントファイルのPath
    """
    cmd_dir = Path(cmd_dir)
    events_dir = cmd_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload_with_ts = {**payload}
    if "timestamp" not in payload_with_ts:
        payload_with_ts["timestamp"] = timestamp

    if validate:
        try:
            schema = load_schema()
            validate_payload(event_type, payload_with_ts, schema)
        except FileNotFoundError:
            pass  # schema.yaml 未配置時はスキップ

    # アトミックSEQ採番: O_CREAT|O_EXCL で競合回避
    for _ in range(100):
        existing = list(events_dir.glob("*.yaml"))
        max_seq = 0
        for f in existing:
            try:
                max_seq = max(max_seq, int(f.name.split("_")[0]))
            except (ValueError, IndexError):
                pass

        seq_str = f"{max_seq + 1:03d}"
        event_path = events_dir / f"{seq_str}_{event_type}.yaml"

        try:
            fd = os.open(str(event_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as e:
            if e.errno == errno.EEXIST:
                continue
            raise

        event_data = {
            "event_type": event_type,
            "timestamp": timestamp,
            "cmd_dir": str(cmd_dir),
            "payload": payload_with_ts,
        }
        content = yaml.dump(
            event_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)

        return event_path

    raise RuntimeError(f"SEQ採番に100回失敗: {event_type}")


def emit_feedback(
    cmd_dir: str | Path,
    source: str,
    content: str,
    feedback_type: str = "info",
) -> Path:
    """
    cmd_dir/feedback/ 以下にフィードバックYAMLを書き出す。
    send_feedback.sh の置換。
    """
    cmd_dir = Path(cmd_dir)
    feedback_dir = cmd_dir / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for _ in range(100):
        existing = list(feedback_dir.glob("*.yaml"))
        max_seq = 0
        for f in existing:
            try:
                max_seq = max(max_seq, int(f.name.split("_")[0]))
            except (ValueError, IndexError):
                pass

        seq_str = f"{max_seq + 1:03d}"
        fb_path = feedback_dir / f"{seq_str}_{feedback_type}.yaml"

        try:
            fd = os.open(str(fb_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as e:
            if e.errno == errno.EEXIST:
                continue
            raise

        feedback_data = {
            "feedback_type": feedback_type,
            "source": source,
            "content": content,
            "timestamp": timestamp,
        }
        yaml_content = yaml.dump(
            feedback_data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        return fb_path

    raise RuntimeError("フィードバックSEQ採番に100回失敗")
