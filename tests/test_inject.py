"""Tests for Learning Engine Wave 3: inject.py"""
import pytest
import yaml
from pathlib import Path
from tanebi.core.inject import (
    load_patterns,
    build_injection_section,
    inject_into_system_prompt,
    INJECTION_MARKER,
)


# ===== Fixtures =====

def _write_pattern(domain_dir: Path, pattern_type: str, seq: int,
                   confidence: float = 0.8, pattern: str = "Test pattern") -> None:
    domain_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "id": f"{pattern_type}_{seq:03d}",
        "type": pattern_type,
        "domain": "coding",
        "pattern": pattern,
        "detail": f"Detail for {pattern_type} {seq}",
        "confidence": confidence,
        "distilled_at": f"2026-01-{seq:02d}",
        "signal_count": 5,
        "source_signals": [],
        "tags": ["coding"],
    }
    (domain_dir / f"{pattern_type}_{seq:03d}.yaml").write_text(
        yaml.dump(data, allow_unicode=True)
    )


# ===== load_patterns のテスト =====

class TestLoadPatterns:
    def test_returns_empty_when_domain_not_exist(self, tmp_path):
        result = load_patterns("nonexistent", tmp_path)
        assert result == {"approach": [], "avoid": [], "decompose": [], "tooling": []}

    def test_loads_approach_patterns(self, tmp_path):
        domain_dir = tmp_path / "learned" / "coding"
        _write_pattern(domain_dir, "approach", 1, confidence=0.9)
        _write_pattern(domain_dir, "approach", 2, confidence=0.7)
        result = load_patterns("coding", tmp_path)
        assert len(result["approach"]) == 2

    def test_sorts_by_confidence_descending(self, tmp_path):
        domain_dir = tmp_path / "learned" / "coding"
        _write_pattern(domain_dir, "approach", 1, confidence=0.6)
        _write_pattern(domain_dir, "approach", 2, confidence=0.9)
        _write_pattern(domain_dir, "approach", 3, confidence=0.75)
        result = load_patterns("coding", tmp_path, sort_by="confidence")
        confidences = [p["confidence"] for p in result["approach"]]
        assert confidences == sorted(confidences, reverse=True)

    def test_respects_limit(self, tmp_path):
        domain_dir = tmp_path / "learned" / "coding"
        for i in range(8):
            _write_pattern(domain_dir, "approach", i + 1, confidence=0.8 - i * 0.05)
        result = load_patterns("coding", tmp_path, limits={"approach": 3, "avoid": 3,
                                                             "decompose": 2, "tooling": 2})
        assert len(result["approach"]) == 3

    def test_loads_multiple_types(self, tmp_path):
        domain_dir = tmp_path / "learned" / "testing"
        _write_pattern(domain_dir, "approach", 1)
        _write_pattern(domain_dir, "avoid", 1)
        _write_pattern(domain_dir, "tooling", 1)
        result = load_patterns("testing", tmp_path)
        assert len(result["approach"]) == 1
        assert len(result["avoid"]) == 1
        assert len(result["tooling"]) == 1

    def test_skips_invalid_yaml(self, tmp_path):
        domain_dir = tmp_path / "learned" / "coding"
        domain_dir.mkdir(parents=True)
        (domain_dir / "broken.yaml").write_text(": invalid: yaml: {{{{")
        result = load_patterns("coding", tmp_path)
        # should not raise, just skip
        assert result["approach"] == []

    def test_default_limits_applied(self, tmp_path):
        domain_dir = tmp_path / "learned" / "coding"
        # approach デフォルト上限は 5
        for i in range(10):
            _write_pattern(domain_dir, "approach", i + 1, confidence=0.9 - i * 0.05)
        result = load_patterns("coding", tmp_path)
        assert len(result["approach"]) <= 5


# ===== build_injection_section のテスト =====

class TestBuildInjectionSection:
    def test_returns_empty_string_when_no_patterns(self):
        patterns = {"approach": [], "avoid": [], "decompose": [], "tooling": []}
        assert build_injection_section(patterns) == ""

    def test_includes_approach_section(self):
        patterns = {
            "approach": [{"pattern": "Test approach", "detail": "Use TDD", "confidence": 0.9}],
            "avoid": [], "decompose": [], "tooling": [],
        }
        text = build_injection_section(patterns)
        assert "推奨アプローチ" in text
        assert "Test approach" in text

    def test_includes_avoid_section(self):
        patterns = {
            "approach": [],
            "avoid": [{"pattern": "Bad pattern", "detail": "Don't do this", "confidence": 0.8}],
            "decompose": [], "tooling": [],
        }
        text = build_injection_section(patterns)
        assert "回避すべきパターン" in text
        assert "Bad pattern" in text

    def test_includes_decompose_section(self):
        patterns = {
            "approach": [], "avoid": [],
            "decompose": [{"pattern": "Schema first", "detail": "Start with schema", "confidence": 0.85}],
            "tooling": [],
        }
        text = build_injection_section(patterns)
        assert "推奨分解パターン" in text

    def test_includes_tooling_section(self):
        patterns = {
            "approach": [], "avoid": [], "decompose": [],
            "tooling": [{"pattern": "Use argparse", "detail": "Lightweight CLI", "confidence": 0.75}],
        }
        text = build_injection_section(patterns)
        assert "推奨ツール構成" in text

    def test_omits_empty_sections(self):
        patterns = {
            "approach": [{"pattern": "Only approach", "detail": "", "confidence": 0.9}],
            "avoid": [], "decompose": [], "tooling": [],
        }
        text = build_injection_section(patterns)
        assert "回避すべきパターン" not in text
        assert "推奨ツール構成" not in text

    def test_multiple_patterns_in_section(self):
        patterns = {
            "approach": [
                {"pattern": "Pattern A", "detail": "Detail A", "confidence": 0.9},
                {"pattern": "Pattern B", "detail": "Detail B", "confidence": 0.8},
            ],
            "avoid": [], "decompose": [], "tooling": [],
        }
        text = build_injection_section(patterns)
        assert "Pattern A" in text
        assert "Pattern B" in text


# ===== inject_into_system_prompt のテスト =====

class TestInjectIntoSystemPrompt:
    def test_returns_original_when_injection_empty(self):
        prompt = "Original system prompt"
        result = inject_into_system_prompt(prompt, "")
        assert result == prompt

    def test_replaces_marker_when_present(self):
        prompt = f"Before\n{INJECTION_MARKER}\nAfter"
        injection = "## Learned Patterns\n- Pattern A"
        result = inject_into_system_prompt(prompt, injection)
        assert INJECTION_MARKER not in result
        assert "Pattern A" in result
        assert "Before" in result
        assert "After" in result

    def test_appends_when_no_marker(self):
        prompt = "Original prompt without marker"
        injection = "## Learned Patterns\n- Pattern A"
        result = inject_into_system_prompt(prompt, injection)
        assert result.startswith("Original prompt without marker")
        assert "Pattern A" in result

    def test_cold_start_no_modification(self):
        prompt = "System prompt for new domain"
        result = inject_into_system_prompt(prompt, "")
        assert result == prompt


# ===== worker.py 統合テスト =====

class TestWorkerIntegration:
    """run_claude_p() の domain/knowledge_dir パラメータを確認するテスト。
    実際の claude -p 呼び出しは行わず、インターフェースのみ確認。"""

    def test_run_claude_p_accepts_domain_param(self):
        """run_claude_p() が domain パラメータを受け取れることを確認"""
        import inspect
        from tanebi.executor.worker import run_claude_p
        sig = inspect.signature(run_claude_p)
        assert "domain" in sig.parameters

    def test_run_claude_p_accepts_knowledge_dir_param(self):
        """run_claude_p() が knowledge_dir パラメータを受け取れることを確認"""
        import inspect
        from tanebi.executor.worker import run_claude_p
        sig = inspect.signature(run_claude_p)
        assert "knowledge_dir" in sig.parameters

    def test_run_claude_p_domain_is_optional(self):
        """domain パラメータはキーワード専用かつデフォルト None"""
        import inspect
        from tanebi.executor.worker import run_claude_p
        sig = inspect.signature(run_claude_p)
        param = sig.parameters["domain"]
        assert param.default is None
