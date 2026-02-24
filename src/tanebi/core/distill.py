"""
Learning Engine Wave 2: Distillation Engine.

Provides functions to trigger, execute, and manage the distillation
of accumulated signals into Learned Patterns.

Note: The LLM-based pattern extraction is designed as a pure function
with an injectable `extractor` callable, enabling easy testing and
future replacement with actual LLM calls.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import yaml


# Default thresholds
DEFAULT_K = 5
DEFAULT_CONFIDENCE_THRESHOLD = 0.6


def check_distill_trigger(
    domain: str,
    knowledge_dir: Path,
    k: int = DEFAULT_K,
) -> bool:
    """
    同一ドメインのシグナル数が K 件以上かどうかを判定する（N≥K ルール）。
    archived/ を除いた未蒸留シグナルのみをカウントする。

    Args:
        domain: 対象ドメイン名
        knowledge_dir: knowledge/ ディレクトリのパス
        k: 蒸留に必要な最小シグナル数（デフォルト 5）

    Returns:
        True if N >= k
    """
    signal_dir = knowledge_dir / "signals" / domain
    if not signal_dir.exists():
        return False
    # archived/ サブディレクトリを除外
    signals = [
        f for f in signal_dir.glob("signal_*.yaml")
        if f.parent == signal_dir  # archived/ の中は除外
    ]
    return len(signals) >= k


def distill(
    domain: str,
    signals: list[dict],
    extractor: Optional[Callable[[str, list[dict]], list[dict]]] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Optional[list[dict]]:
    """
    シグナル群からパターンを抽出し Learned Patterns を生成する。

    蒸留プロセス:
      1. パターン収束分析（positive vs negative 比率）
      2. 抽象化（具体的な ID・パスを除去）
      3. 信頼度算出（confidence = 多数派シグナル数 / 総数）
      4. confidence < threshold の場合は保留（None を返す）
      5. Learned Pattern 辞書リストを生成

    Args:
        domain: 対象ドメイン名
        signals: シグナル辞書のリスト（detect_signal() の出力）
        extractor: LLM ベースのパターン抽出関数（None の場合はデフォルト実装を使用）
                   シグネチャ: (domain: str, signals: list[dict]) -> list[dict]
        confidence_threshold: 蒸留に必要な最小信頼度（デフォルト 0.6）

    Returns:
        Learned Pattern 辞書のリスト、または None（信頼度不足・矛盾検出時）
    """
    if not signals:
        return None

    # デフォルト extractor: シグナルの多数決から簡易パターンを生成
    if extractor is None:
        extractor = _default_extractor

    # 信頼度算出: 多数派の signal_type の割合
    positive_count = sum(1 for s in signals if s.get("signal_type") in ("positive", "weak_positive"))
    negative_count = sum(1 for s in signals if s.get("signal_type") == "negative")
    total = len(signals)

    dominant = positive_count if positive_count >= negative_count else negative_count
    confidence = dominant / total if total > 0 else 0.0

    # 矛盾検出: positive と negative が拮抗（±10% 以内）
    if total >= 2 and abs(positive_count - negative_count) <= max(1, total * 0.1):
        return None  # 矛盾あり、保留

    # 信頼度不足
    if confidence < confidence_threshold:
        return None

    return extractor(domain, signals)


def save_learned_pattern(
    pattern: dict,
    domain: str,
    knowledge_dir: Path,
) -> Path:
    """
    Learned Pattern を knowledge/learned/{domain}/ に YAML ファイルとして書き出す。

    ファイル名: {type}_{seq:03d}.yaml
    例: approach_001.yaml, avoid_002.yaml

    Args:
        pattern: Learned Pattern 辞書
        domain: 対象ドメイン名
        knowledge_dir: knowledge/ ディレクトリのパス

    Returns:
        書き出したファイルのパス
    """
    domain_dir = knowledge_dir / "learned" / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    pattern_type = pattern.get("type", "approach")
    existing = sorted(domain_dir.glob(f"{pattern_type}_*.yaml"))
    seq = len(existing) + 1

    filename = f"{pattern_type}_{seq:03d}.yaml"
    filepath = domain_dir / filename

    while filepath.exists():
        seq += 1
        filename = f"{pattern_type}_{seq:03d}.yaml"
        filepath = domain_dir / filename

    record = {
        "id": f"{pattern_type}_{seq:03d}",
        "type": pattern_type,
        "domain": domain,
        "pattern": pattern.get("pattern", ""),
        "detail": pattern.get("detail", ""),
        "signal_count": pattern.get("signal_count", 0),
        "confidence": pattern.get("confidence", 0.0),
        "distilled_at": datetime.now(timezone.utc).date().isoformat(),
        "source_signals": pattern.get("source_signals", []),
        "tags": pattern.get("tags", []),
    }

    filepath.write_text(yaml.dump(record, allow_unicode=True, default_flow_style=False))
    return filepath


def archive_signals(
    signal_ids: list[str],
    domain: str,
    knowledge_dir: Path,
) -> list[Path]:
    """
    蒸留済みシグナルを knowledge/signals/{domain}/archived/ に移動する。

    Args:
        signal_ids: アーカイブ対象のシグナル ID リスト（例: ["signal_20260115_001"]）
        domain: 対象ドメイン名
        knowledge_dir: knowledge/ ディレクトリのパス

    Returns:
        移動先ファイルパスのリスト
    """
    signal_dir = knowledge_dir / "signals" / domain
    archive_dir = signal_dir / "archived"
    archive_dir.mkdir(parents=True, exist_ok=True)

    moved = []
    for signal_id in signal_ids:
        src = signal_dir / f"{signal_id}.yaml"
        if src.exists():
            dst = archive_dir / f"{signal_id}.yaml"
            shutil.move(str(src), str(dst))
            moved.append(dst)
    return moved


def log_distillation(
    domain: str,
    pattern_ids: list[str],
    knowledge_dir: Path,
    signal_count: int,
    confidence: float,
) -> None:
    """
    蒸留実行ログを knowledge/_meta/distill_log.yaml に追記する。

    Args:
        domain: 蒸留対象ドメイン
        pattern_ids: 生成された Learned Pattern ID リスト
        knowledge_dir: knowledge/ ディレクトリのパス
        signal_count: 蒸留に使ったシグナル数
        confidence: 蒸留時の信頼度
    """
    meta_dir = knowledge_dir / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    log_path = meta_dir / "distill_log.yaml"

    if log_path.exists():
        existing = yaml.safe_load(log_path.read_text()) or {}
        entries = existing.get("entries", [])
    else:
        entries = []

    entries.append({
        "domain": domain,
        "distilled_at": datetime.now(timezone.utc).isoformat(),
        "signal_count": signal_count,
        "patterns_created": pattern_ids,
        "confidence": confidence,
    })

    log_path.write_text(yaml.dump({"entries": entries}, allow_unicode=True, default_flow_style=False))


# --- Internal helpers ---

def _default_extractor(domain: str, signals: list[dict]) -> list[dict]:
    """
    デフォルトのパターン抽出器（LLM なし、ヒューリスティックベース）。
    正例群・負例群それぞれから1パターンを生成する。

    本番では LLM ベースの extractor に差し替えること。
    """
    patterns = []
    positive = [s for s in signals if s.get("signal_type") in ("positive", "weak_positive")]
    negative = [s for s in signals if s.get("signal_type") == "negative"]
    total = len(signals)

    if positive:
        confidence = len(positive) / total
        patterns.append({
            "type": "approach",
            "domain": domain,
            "pattern": _summarize_contexts([s.get("abstracted_context", "") for s in positive]),
            "detail": f"{len(positive)}件の成功シグナルから抽出。",
            "signal_count": len(positive),
            "confidence": round(confidence, 3),
            "source_signals": [s.get("id", "") for s in positive if s.get("id")],
            "tags": [domain],
        })

    if negative:
        confidence = len(negative) / total
        patterns.append({
            "type": "avoid",
            "domain": domain,
            "pattern": _summarize_contexts([s.get("abstracted_context", "") for s in negative]),
            "detail": f"{len(negative)}件の失敗シグナルから抽出。",
            "signal_count": len(negative),
            "confidence": round(confidence, 3),
            "source_signals": [s.get("id", "") for s in negative if s.get("id")],
            "tags": [domain],
        })

    return patterns if patterns else None


def _summarize_contexts(contexts: list[str]) -> str:
    """コンテキスト群を簡易集約する（プレースホルダ実装）。"""
    non_empty = [c for c in contexts if c]
    if not non_empty:
        return ""
    # 最初の非空コンテキストを代表として返す（本番では LLM で要約）
    return non_empty[0][:100]
