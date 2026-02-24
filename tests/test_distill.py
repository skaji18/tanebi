"""Tests for Learning Engine Wave 2: distill.py"""
import pytest
from pathlib import Path
from tanebi.core.distill import (
    check_distill_trigger,
    distill,
    save_learned_pattern,
    archive_signals,
    log_distillation,
)


# ===== check_distill_trigger のテスト =====

class TestCheckDistillTrigger:
    def test_returns_false_when_domain_not_exist(self, tmp_path):
        assert check_distill_trigger("nonexistent", tmp_path) is False

    def test_returns_false_when_below_k(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        for i in range(3):
            (domain_dir / f"signal_20260101_{i:03d}.yaml").write_text("id: x")
        assert check_distill_trigger("coding", tmp_path, k=5) is False

    def test_returns_true_when_equal_to_k(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        for i in range(5):
            (domain_dir / f"signal_20260101_{i:03d}.yaml").write_text("id: x")
        assert check_distill_trigger("coding", tmp_path, k=5) is True

    def test_returns_true_when_above_k(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        for i in range(8):
            (domain_dir / f"signal_20260101_{i:03d}.yaml").write_text("id: x")
        assert check_distill_trigger("coding", tmp_path, k=5) is True

    def test_excludes_archived_signals(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        archived_dir = domain_dir / "archived"
        domain_dir.mkdir(parents=True)
        archived_dir.mkdir(parents=True)
        # 2 active + 5 archived = only active counted
        for i in range(2):
            (domain_dir / f"signal_20260101_{i:03d}.yaml").write_text("id: x")
        for i in range(5):
            (archived_dir / f"signal_20260102_{i:03d}.yaml").write_text("id: x")
        assert check_distill_trigger("coding", tmp_path, k=5) is False


# ===== distill のテスト =====

class TestDistill:
    def _make_signal(self, signal_type, context="test context", sid=None):
        return {
            "id": sid or f"signal_{signal_type}_001",
            "signal_type": signal_type,
            "domain": "coding",
            "abstracted_context": context,
        }

    def test_returns_none_when_empty(self):
        assert distill("coding", []) is None

    def test_returns_none_below_confidence(self):
        # 3 positive + 3 negative = confidence 0.5 < 0.6
        signals = (
            [self._make_signal("positive")] * 3
            + [self._make_signal("negative")] * 3
        )
        assert distill("coding", signals) is None

    def test_returns_none_when_contradicting(self):
        # 5 positive vs 5 negative — 拮抗
        signals = (
            [self._make_signal("positive")] * 5
            + [self._make_signal("negative")] * 5
        )
        assert distill("coding", signals) is None

    def test_returns_patterns_with_dominant_positive(self):
        signals = [self._make_signal("positive")] * 7 + [self._make_signal("negative")] * 2
        result = distill("coding", signals)
        assert result is not None
        assert len(result) >= 1
        types = [p["type"] for p in result]
        assert "approach" in types

    def test_returns_patterns_with_dominant_negative(self):
        signals = [self._make_signal("negative")] * 6 + [self._make_signal("positive")] * 1
        result = distill("coding", signals)
        assert result is not None
        types = [p["type"] for p in result]
        assert "avoid" in types

    def test_custom_extractor_called(self):
        called = []
        def mock_extractor(domain, signals):
            called.append((domain, len(signals)))
            return [{"type": "approach", "domain": domain, "pattern": "mock",
                      "detail": "", "signal_count": len(signals),
                      "confidence": 0.9, "source_signals": [], "tags": []}]

        signals = [self._make_signal("positive")] * 5
        result = distill("coding", signals, extractor=mock_extractor)
        assert len(called) == 1
        assert called[0][0] == "coding"
        assert result is not None

    def test_confidence_threshold_respected(self):
        # 6/10 = 0.6 → at threshold, should pass with default 0.6
        signals = [self._make_signal("positive")] * 6 + [self._make_signal("negative")] * 4
        result = distill("coding", signals, confidence_threshold=0.6)
        assert result is not None

    def test_below_custom_confidence_threshold(self):
        # 6/10 = 0.6, threshold 0.7 → should fail
        signals = [self._make_signal("positive")] * 6 + [self._make_signal("negative")] * 4
        result = distill("coding", signals, confidence_threshold=0.7)
        assert result is None


# ===== save_learned_pattern のテスト =====

class TestSaveLearnedPattern:
    def _make_pattern(self, pattern_type="approach"):
        return {
            "type": pattern_type,
            "domain": "coding",
            "pattern": "Test pattern",
            "detail": "Test detail",
            "signal_count": 5,
            "confidence": 0.8,
            "source_signals": ["signal_001"],
            "tags": ["coding"],
        }

    def test_creates_file_in_domain_dir(self, tmp_path):
        pattern = self._make_pattern("approach")
        path = save_learned_pattern(pattern, "coding", tmp_path)
        assert path.exists()
        assert path.parent.name == "coding"
        assert path.parent.parent.name == "learned"

    def test_filename_matches_type(self, tmp_path):
        pattern = self._make_pattern("avoid")
        path = save_learned_pattern(pattern, "coding", tmp_path)
        assert path.name.startswith("avoid_")

    def test_saved_yaml_is_valid(self, tmp_path):
        import yaml
        pattern = self._make_pattern("approach")
        path = save_learned_pattern(pattern, "coding", tmp_path)
        content = yaml.safe_load(path.read_text())
        assert content["type"] == "approach"
        assert content["pattern"] == "Test pattern"
        assert "distilled_at" in content

    def test_multiple_patterns_get_unique_filenames(self, tmp_path):
        pattern = self._make_pattern("approach")
        path1 = save_learned_pattern(pattern, "coding", tmp_path)
        path2 = save_learned_pattern(pattern, "coding", tmp_path)
        assert path1 != path2

    def test_creates_domain_dir_if_missing(self, tmp_path):
        pattern = self._make_pattern("decompose")
        path = save_learned_pattern(pattern, "new_domain", tmp_path)
        assert path.exists()


# ===== archive_signals のテスト =====

class TestArchiveSignals:
    def test_moves_signal_to_archived(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        (domain_dir / "signal_20260101_001.yaml").write_text("id: signal_20260101_001")

        moved = archive_signals(["signal_20260101_001"], "coding", tmp_path)
        assert len(moved) == 1
        assert moved[0].exists()
        assert moved[0].parent.name == "archived"
        assert not (domain_dir / "signal_20260101_001.yaml").exists()

    def test_ignores_missing_signal_ids(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        # signal_nonexistent は存在しない
        moved = archive_signals(["signal_nonexistent"], "coding", tmp_path)
        assert moved == []

    def test_creates_archived_dir_if_missing(self, tmp_path):
        domain_dir = tmp_path / "signals" / "coding"
        domain_dir.mkdir(parents=True)
        (domain_dir / "signal_20260101_001.yaml").write_text("id: x")
        archive_signals(["signal_20260101_001"], "coding", tmp_path)
        assert (domain_dir / "archived").is_dir()


# ===== log_distillation のテスト =====

class TestLogDistillation:
    def test_creates_log_file(self, tmp_path):
        log_distillation("coding", ["approach_001"], tmp_path, signal_count=5, confidence=0.8)
        log_path = tmp_path / "_meta" / "distill_log.yaml"
        assert log_path.exists()

    def test_log_entry_content(self, tmp_path):
        import yaml
        log_distillation("testing", ["avoid_001", "approach_001"], tmp_path,
                         signal_count=7, confidence=0.85)
        log_path = tmp_path / "_meta" / "distill_log.yaml"
        content = yaml.safe_load(log_path.read_text())
        assert len(content["entries"]) == 1
        entry = content["entries"][0]
        assert entry["domain"] == "testing"
        assert entry["signal_count"] == 7
        assert "approach_001" in entry["patterns_created"]

    def test_appends_multiple_entries(self, tmp_path):
        import yaml
        log_distillation("coding", ["approach_001"], tmp_path, signal_count=5, confidence=0.8)
        log_distillation("testing", ["avoid_001"], tmp_path, signal_count=6, confidence=0.75)
        log_path = tmp_path / "_meta" / "distill_log.yaml"
        content = yaml.safe_load(log_path.read_text())
        assert len(content["entries"]) == 2
