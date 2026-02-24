"""
Learning Engine Wave 1: Signal Detection and Accumulation.

Provides functions to detect, classify, and accumulate signals
from worker.completed and checkpoint.completed events.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


def detect_signal(event: dict) -> Optional[dict]:
    """
    worker.completed / checkpoint.completed イベントからシグナルを抽出する。
    対象外イベントは None を返す。

    Args:
        event: イベントYAMLを読み込んだ辞書（payload フィールドを含む）

    Returns:
        シグナル辞書 or None
    """
    event_type = event.get("type", "")
    payload = event.get("payload", {})

    if event_type == "worker.completed":
        quality = payload.get("quality", "")
        status = payload.get("status", "")
        signal_type, weight = classify_signal(quality, status)
        return {
            "domain": payload.get("domain", "general"),
            "task_id": payload.get("task_id", ""),
            "subtask_id": payload.get("subtask_id", ""),
            "quality": quality,
            "status": status,
            "signal_type": signal_type,
            "weight": weight,
            "abstracted_context": _abstract_context(payload.get("summary", "")),
            "observation": "",
            "source_event": event_type,
        }

    elif event_type == "checkpoint.completed":
        verdict = payload.get("verdict", "")
        quality = "GREEN" if verdict == "PASS" else "RED"
        status = "success" if verdict == "PASS" else "failure"
        signal_type, weight = "checkpoint_feedback", 1.0
        return {
            "domain": payload.get("domain", "general"),
            "task_id": payload.get("task_id", ""),
            "subtask_id": payload.get("subtask_id", ""),
            "quality": quality,
            "status": status,
            "signal_type": signal_type,
            "weight": weight,
            "abstracted_context": _abstract_context(payload.get("summary", "")),
            "observation": "",
            "attribution": payload.get("attribution", ""),
            "round": payload.get("round", 0),
            "source_event": event_type,
        }

    return None


def classify_signal(quality: str, status: str) -> tuple[str, float]:
    """
    quality と status からシグナル種別と weight を決定する。

    分類表:
      GREEN  + success  -> positive        / 1.0
      YELLOW + success  -> weak_positive   / 0.5
      RED    + failure  -> negative        / 1.0
      その他             -> negative        / 0.5 (フォールバック)

    Returns:
        (signal_type, weight) のタプル
    """
    if quality == "GREEN" and status == "success":
        return "positive", 1.0
    elif quality == "YELLOW" and status == "success":
        return "weak_positive", 0.5
    elif quality == "RED" and status == "failure":
        return "negative", 1.0
    else:
        return "negative", 0.5


def accumulate_signal(signal: dict, knowledge_dir: Path) -> Path:
    """
    シグナルをドメイン別ディレクトリに YAML ファイルとして書き出す。
    シグナルファイルは immutable（追記のみ、書き換えなし）。

    Args:
        signal: detect_signal() が返したシグナル辞書
        knowledge_dir: knowledge/ ディレクトリのパス

    Returns:
        書き出したファイルのパス
    """
    domain = signal.get("domain", "general")
    domain_dir = knowledge_dir / "signals" / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    # ファイル名: signal_{YYYYMMDD}_{seq:03d}.yaml
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    existing = sorted(domain_dir.glob(f"signal_{today}_*.yaml"))
    seq = len(existing) + 1
    filename = f"signal_{today}_{seq:03d}.yaml"
    filepath = domain_dir / filename

    # immutable: ファイルが既に存在する場合は連番を進める
    while filepath.exists():
        seq += 1
        filename = f"signal_{today}_{seq:03d}.yaml"
        filepath = domain_dir / filename

    record = {
        "id": f"signal_{today}_{seq:03d}",
        "type": "signal",
        "domain": domain,
        "task_id": signal.get("task_id", ""),
        "subtask_id": signal.get("subtask_id", ""),
        "quality": signal.get("quality", ""),
        "status": signal.get("status", ""),
        "weight": signal.get("weight", 1.0),
        "signal_type": signal.get("signal_type", ""),
        "abstracted_context": signal.get("abstracted_context", ""),
        "observation": signal.get("observation", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # checkpoint_feedback のみ追加フィールドを持つ
    if signal.get("signal_type") == "checkpoint_feedback":
        record["attribution"] = signal.get("attribution", "")
        record["round"] = signal.get("round", 0)

    filepath.write_text(yaml.dump(record, allow_unicode=True, default_flow_style=False))
    return filepath


def _abstract_context(text: str) -> str:
    """
    タスク説明から具体的なファイル名・変数名等を除去した抽象表現を生成する。
    簡易実装: ファイルパス・関数名・数値リテラルを汎用表現に置換。
    """
    if not text:
        return ""
    # ファイルパス除去
    text = re.sub(r"[~/][\w./\-]+\.\w+", "<file>", text)
    # モジュール名/変数名は保持し、抽象化はシンプルに
    return text[:200].strip()
