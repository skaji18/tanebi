"""tanebi.core.fitness のユニットテスト"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tanebi.core.fitness import (
    DEFAULT_WEIGHTS,
    DEFAULT_WINDOW,
    calculate_fitness,
    load_fitness_config,
    update_persona_fitness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(n: int, status: str = "success", quality: str = "GREEN") -> list[dict]:
    """指定パラメータでタスク履歴を生成。"""
    return [
        {"status": status, "quality": quality, "domain": "python", "duration_estimate": ""}
        for _ in range(n)
    ]


def _make_persona_yaml(tmp_path: Path, persona_id: str, **extra) -> Path:
    """テスト用ペルソナYAMLをtmp_pathに作成してPathを返す。"""
    data = {
        "persona": {
            "id": persona_id,
            "base_model": "claude-sonnet-4-6",
            "version": 1,
            "created_at": "2026-01-01T00:00:00",
            "parent_version": None,
            "lineage": [],
            "identity": {
                "name": f"Test {persona_id}",
                "speech_style": "冷静",
                "archetype": "generalist",
                "origin": "seeded",
            },
            "knowledge": {
                "domains": [
                    {"name": "python", "proficiency": 0.8, "task_count": 5, "last_updated": "2026-01-01"},
                ],
                "few_shot_refs": [],
                "anti_patterns": [],
            },
            "behavior": {
                "risk_tolerance": 0.5,
                "detail_orientation": 0.7,
                "speed_vs_quality": 0.6,
                "autonomy_preference": 0.8,
                "communication_density": 0.4,
            },
            **extra,
        }
    }
    p = tmp_path / f"{persona_id}.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# calculate_fitness
# ---------------------------------------------------------------------------

class TestCalculateFitness:
    def test_no_history_returns_base_score(self):
        """タスク履歴なし時にドメイン習熟度ベースのスコアを返す。"""
        persona_data = {
            "knowledge": {
                "domains": [{"name": "python", "proficiency": 0.8}]
            }
        }
        score = calculate_fitness(persona_data, [], weights=DEFAULT_WEIGHTS, window=DEFAULT_WINDOW)
        expected = round(0.8 * 0.5, 4)
        assert score == expected

    def test_no_history_no_domains_returns_025(self):
        """履歴なし・ドメインなし時は 0.25 を返す。"""
        score = calculate_fitness({}, [], weights=DEFAULT_WEIGHTS, window=DEFAULT_WINDOW)
        assert score == 0.25

    def test_all_green_high_score(self):
        """全GREEN成功履歴ではスコアが高い（0.7以上）。"""
        history = _make_history(10, "success", "GREEN")
        score = calculate_fitness({}, history, weights=DEFAULT_WEIGHTS, window=DEFAULT_WINDOW)
        assert score >= 0.7

    def test_all_red_failed_low_score(self):
        """全RED失敗履歴ではスコアが低い（0.3未満）。"""
        history = _make_history(10, "failed", "RED")
        score = calculate_fitness({}, history, weights=DEFAULT_WEIGHTS, window=DEFAULT_WINDOW)
        assert score < 0.3

    def test_uses_window(self):
        """windowサイズで直近N件のみ使用し、古い件は無視される。"""
        # 古い5件: 全失敗RED / 新しい5件: 全成功GREEN
        old = _make_history(5, "failed", "RED")
        recent = _make_history(5, "success", "GREEN")
        history = old + recent

        # window=5: 新しいGREENのみ → 高スコア
        score_small = calculate_fitness({}, history, weights=DEFAULT_WEIGHTS, window=5)
        # window=20: 全10件（混在）→ 低スコア
        score_large = calculate_fitness({}, history, weights=DEFAULT_WEIGHTS, window=20)
        assert score_small > score_large

    def test_score_clamped_between_0_and_1(self):
        """スコアは必ず0.0〜1.0の範囲に収まる。"""
        history = _make_history(5, "success", "GREEN")
        score = calculate_fitness({}, history)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# load_fitness_config
# ---------------------------------------------------------------------------

class TestLoadFitnessConfig:
    def test_defaults_when_no_config(self, tmp_path: Path):
        """config.yaml未指定時（存在しない）はデフォルト値を返す。"""
        weights, window = load_fitness_config(tanebi_root=tmp_path)
        assert weights == DEFAULT_WEIGHTS
        assert window == DEFAULT_WINDOW

    def test_reads_fitness_weights_from_config(self, tmp_path: Path):
        """config.yamlのfitness_weightsを正しく読み取る。"""
        config = {
            "tanebi": {
                "evolution": {
                    "fitness_weights": {
                        "quality_score": 0.50,
                        "completion_rate": 0.20,
                        "efficiency": 0.20,
                        "growth_rate": 0.10,
                    },
                    "fitness_window": 15,
                }
            }
        }
        (tmp_path / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")
        weights, window = load_fitness_config(tanebi_root=tmp_path)
        assert weights["quality_score"] == pytest.approx(0.50)
        assert weights["completion_rate"] == pytest.approx(0.20)
        assert window == 15

    def test_returns_tuple_types(self, tmp_path: Path):
        """戻り値の型が (dict, int) であることを確認。"""
        weights, window = load_fitness_config(tanebi_root=tmp_path)
        assert isinstance(weights, dict)
        assert isinstance(window, int)


# ---------------------------------------------------------------------------
# update_persona_fitness (M-015 確認: yaml.safe_load/dump 使用)
# ---------------------------------------------------------------------------

class TestUpdatePersonaFitness:
    def test_uses_yaml_safe_load_and_dump(self, tmp_path: Path):
        """update_persona_fitnessがyaml.safe_load/dumpを使用し、evolution.*を正しく書き戻す。"""
        persona_path = _make_persona_yaml(tmp_path, "test_persona")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        score = update_persona_fitness(persona_path, work_dir=work_dir)

        # yaml.safe_loadで読み直して検証（M-015: regex不使用確認）
        with persona_path.open(encoding="utf-8") as f:
            result = yaml.safe_load(f)

        assert isinstance(result, dict)
        persona = result.get("persona", {})
        evolution = persona.get("evolution", {})

        assert "fitness_score" in evolution, "evolution.fitness_score が書き込まれていない"
        assert evolution["fitness_score"] == score
        assert "last_updated" in evolution, "evolution.last_updated が書き込まれていない"
        assert isinstance(evolution["last_updated"], str)

    def test_fitness_score_is_float_in_valid_range(self, tmp_path: Path):
        """返却値がfloatであり0.0〜1.0の範囲内であることを確認。"""
        persona_path = _make_persona_yaml(tmp_path, "test_persona2")
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        score = update_persona_fitness(persona_path, work_dir=work_dir)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_evolution_section_created_if_absent(self, tmp_path: Path):
        """evolutionセクションがない場合に新規作成されることを確認。"""
        # evolutionなしのシンプルなペルソナ
        data = {
            "persona": {
                "id": "no_evo",
                "knowledge": {"domains": [{"name": "go", "proficiency": 0.6}]},
            }
        }
        persona_path = tmp_path / "no_evo.yaml"
        persona_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

        work_dir = tmp_path / "work"
        work_dir.mkdir()
        update_persona_fitness(persona_path, work_dir=work_dir)

        with persona_path.open(encoding="utf-8") as f:
            result = yaml.safe_load(f)

        assert "evolution" in result["persona"]
        assert "fitness_score" in result["persona"]["evolution"]
