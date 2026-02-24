"""TANEBI Executor Worker — claude -p サブプロセス実行"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


class WorkerError(Exception):
    """claude -p 実行失敗時の例外"""
    pass


def read_template(template_name: str) -> str:
    """~/projects/tanebi/templates/{template_name} を読み込んで返す。

    ファイルが存在しない場合は FileNotFoundError をそのまま伝播。
    """
    tanebi_root = Path(__file__).parent.parent.parent.parent
    template_path = tanebi_root / "templates" / template_name
    with template_path.open(encoding="utf-8") as f:
        return f.read()


def run_claude_p(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
    allowed_tools: str = "Read,Write,Glob,Grep,Bash",
    domain: str | None = None,
    knowledge_dir: Path | None = None,
) -> str:
    """claude -p をサブプロセスで実行し、stdout を返す。

    - shell=False でシェルインジェクション防止
    - CLAUDECODE / CLAUDE_CODE_ENTRYPOINT を env から除去（既知バグ対策）
    - user_prompt は stdin (input=) で渡す
    - returncode != 0 のとき WorkerError を送出
    """
    from tanebi.config import load_config
    cfg = load_config()
    exec_cfg = cfg.get("tanebi", {}).get("execution", {})
    model = model or exec_cfg.get("default_model", "claude-sonnet-4-6")
    timeout = timeout or exec_cfg.get("timeout", 300)

    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}

    # Silent injection: load Learned Patterns if domain is specified
    if domain and knowledge_dir:
        try:
            from tanebi.core.inject import load_patterns, build_injection_section, inject_into_system_prompt
            patterns = load_patterns(domain, knowledge_dir)
            injection_text = build_injection_section(patterns)
            system_prompt = inject_into_system_prompt(system_prompt, injection_text)
        except Exception:
            pass  # 注入失敗でも Worker は正常動作する

    cmd = [
        "claude", "-p",
        "--model", model,
        "--output-format", "text",
        "--system-prompt", system_prompt,
        "--allowed-tools", allowed_tools,
    ]

    result = subprocess.run(
        cmd,
        input=user_prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        shell=False,
    )

    if result.returncode != 0:
        raise WorkerError(
            f"claude -p failed (returncode={result.returncode}): {result.stderr.strip()}"
        )

    return result.stdout
