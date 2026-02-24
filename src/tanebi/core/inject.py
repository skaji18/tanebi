"""
Learning Engine Wave 3: Silent Injection.

Loads Learned Patterns from knowledge/learned/{domain}/
and injects them silently into Worker system prompts.
Workers are unaware of the injection — they simply receive
enriched context as part of their normal prompt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


# Default injection limits (matching config.yaml.example)
DEFAULT_LIMITS = {
    "approach": 5,
    "avoid": 3,
    "decompose": 2,
    "tooling": 2,
}

# Placeholder marker inserted into templates
INJECTION_MARKER = "<!-- LEARNED_PATTERNS_SECTION -->"


def load_patterns(
    domain: str,
    knowledge_dir: Path,
    limits: Optional[dict[str, int]] = None,
    sort_by: str = "confidence",
) -> dict[str, list[dict]]:
    """
    knowledge/learned/{domain}/ から Learned Patterns を読み込む。

    confidence 順でソートし、limits で指定された上限数に切り詰める。

    Args:
        domain: 対象ドメイン名
        knowledge_dir: knowledge/ ディレクトリのパス
        limits: 種別ごとの上限 {"approach": 5, "avoid": 3, ...}
                None の場合は DEFAULT_LIMITS を使用
        sort_by: ソートキー（"confidence" or "distilled_at"）

    Returns:
        {"approach": [...], "avoid": [...], "decompose": [...], "tooling": [...]}
        各リストは上限内の上位パターン辞書
    """
    limits = limits or DEFAULT_LIMITS
    learned_dir = knowledge_dir / "learned" / domain

    result: dict[str, list[dict]] = {
        pattern_type: [] for pattern_type in DEFAULT_LIMITS
    }

    if not learned_dir.exists():
        return result

    for yaml_file in sorted(learned_dir.glob("*.yaml")):
        try:
            pattern = yaml.safe_load(yaml_file.read_text())
        except Exception:
            continue
        if not isinstance(pattern, dict):
            continue
        pattern_type = pattern.get("type", "")
        if pattern_type in result:
            result[pattern_type].append(pattern)

    # ソート＋切り詰め
    for pattern_type, patterns in result.items():
        if sort_by == "confidence":
            patterns.sort(key=lambda p: p.get("confidence", 0.0), reverse=True)
        else:
            patterns.sort(key=lambda p: p.get("distilled_at", ""), reverse=True)
        limit = limits.get(pattern_type, DEFAULT_LIMITS.get(pattern_type, 5))
        result[pattern_type] = patterns[:limit]

    return result


def build_injection_section(patterns: dict[str, list[dict]]) -> str:
    """
    パターン辞書から注入用 Markdown テキストを生成する。

    注入なしの場合（全パターンが空）は空文字列を返す。

    Args:
        patterns: load_patterns() の戻り値

    Returns:
        Markdown 形式の注入テキスト（空の場合は ""）
    """
    sections = []

    approach_list = patterns.get("approach", [])
    if approach_list:
        lines = ["## 推奨アプローチ（Learned Patterns）", ""]
        for p in approach_list:
            lines.append(f"- **{p.get('pattern', '')}**")
            if p.get("detail"):
                # 1行目のみ (detail は長い場合があるので先頭100文字)
                detail_first = p["detail"].strip().split("\n")[0][:100]
                lines.append(f"  {detail_first}")
        sections.append("\n".join(lines))

    avoid_list = patterns.get("avoid", [])
    if avoid_list:
        lines = ["## 回避すべきパターン（Learned Patterns）", ""]
        for p in avoid_list:
            lines.append(f"- **{p.get('pattern', '')}**")
            if p.get("detail"):
                detail_first = p["detail"].strip().split("\n")[0][:100]
                lines.append(f"  {detail_first}")
        sections.append("\n".join(lines))

    decompose_list = patterns.get("decompose", [])
    if decompose_list:
        lines = ["## 推奨分解パターン（Learned Patterns）", ""]
        for p in decompose_list:
            lines.append(f"- **{p.get('pattern', '')}**")
            if p.get("detail"):
                detail_first = p["detail"].strip().split("\n")[0][:100]
                lines.append(f"  {detail_first}")
        sections.append("\n".join(lines))

    tooling_list = patterns.get("tooling", [])
    if tooling_list:
        lines = ["## 推奨ツール構成（Learned Patterns）", ""]
        for p in tooling_list:
            lines.append(f"- **{p.get('pattern', '')}**")
            if p.get("detail"):
                detail_first = p["detail"].strip().split("\n")[0][:100]
                lines.append(f"  {detail_first}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n".join(sections)


def inject_into_system_prompt(
    system_prompt: str,
    injection_text: str,
) -> str:
    """
    system_prompt に Learned Patterns テキストを注入する。

    注入戦略:
    1. INJECTION_MARKER が存在する場合 → マーカーを injection_text で置換
    2. マーカーが存在しない場合 → プロンプト末尾に追記

    injection_text が空の場合は system_prompt をそのまま返す（Cold Start 対応）。

    Args:
        system_prompt: 元のシステムプロンプト
        injection_text: build_injection_section() の戻り値

    Returns:
        注入済みシステムプロンプト
    """
    if not injection_text:
        return system_prompt

    if INJECTION_MARKER in system_prompt:
        return system_prompt.replace(INJECTION_MARKER, injection_text)

    return system_prompt + "\n\n" + injection_text
