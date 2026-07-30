from __future__ import annotations

import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from reposcale.schemas import CommandResult


def run_command(command: str, cwd: Path, timeout_seconds: float) -> CommandResult:
    resolved_cwd = cwd.resolve()
    if not resolved_cwd.exists() or not resolved_cwd.is_dir():
        raise ValueError(f"command cwd must be an existing directory: {cwd}")

    started_at = datetime.now(timezone.utc)
    started_timer = perf_counter()
    process = subprocess.Popen(
        command,
        cwd=resolved_cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        stop_process_tree(process)
        stdout, stderr = process.communicate()
        completed_at = datetime.now(timezone.utc)
        return CommandResult(
            command=command,
            cwd=resolved_cwd,
            exit_code=None,
            timed_out=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=perf_counter() - started_timer,
            stdout=stdout,
            stderr=stderr,
        )

    completed_at = datetime.now(timezone.utc)
    return CommandResult(
        command=command,
        cwd=resolved_cwd,
        exit_code=process.returncode,
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=perf_counter() - started_timer,
        stdout=stdout,
        stderr=stderr,
    )


def stop_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            text=True,
        )
        return

    os.killpg(process.pid, signal.SIGTERM)
