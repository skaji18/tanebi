"""Tests for tanebi persona CLI subcommand."""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch


def test_persona_list_empty(capsys):
    """list_personas が [] を返す時に正常終了（returncode=0）"""
    with patch("tanebi.core.persona_ops.list_personas", return_value=[]):
        from tanebi.cli.persona_cmd import _persona_list
        args = argparse.Namespace()
        _persona_list(args)
    captured = capsys.readouterr()
    assert "no personas" in captured.out


def test_persona_copy_invokes_copy_persona():
    """copy_persona がモックで呼ばれる"""
    with patch("tanebi.core.persona_ops.copy_persona", return_value=Path("/tmp/dst.yaml")) as mock_copy:
        from tanebi.cli.persona_cmd import _persona_copy
        args = argparse.Namespace(src="alpha", dst="beta")
        _persona_copy(args)
    mock_copy.assert_called_once_with("alpha", "beta")


def test_persona_merge_invokes_merge_personas():
    """merge_personas がモックで呼ばれる"""
    with patch("tanebi.core.persona_ops.merge_personas", return_value=Path("/tmp/out.yaml")) as mock_merge:
        from tanebi.cli.persona_cmd import _persona_merge
        args = argparse.Namespace(base="alpha", donor="beta", output=None)
        _persona_merge(args)
    mock_merge.assert_called_once_with("alpha", "beta", "alpha_x_beta")


def test_persona_merge_with_explicit_output():
    """--output 指定時は指定されたIDが使われる"""
    with patch("tanebi.core.persona_ops.merge_personas", return_value=Path("/tmp/out.yaml")) as mock_merge:
        from tanebi.cli.persona_cmd import _persona_merge
        args = argparse.Namespace(base="alpha", donor="beta", output="custom_out")
        _persona_merge(args)
    mock_merge.assert_called_once_with("alpha", "beta", "custom_out")
