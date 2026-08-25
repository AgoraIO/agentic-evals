"""Workspace-scoped acpx commands used by the OpenClaw evaluator."""

import os
import subprocess
import sys
from pathlib import Path


class AcpxCommandError(RuntimeError):
    def __init__(self, command, returncode, stderr):
        detail = stderr.strip() or "no stderr"
        super().__init__(
            f"acpx setup command failed with exit {returncode}: "
            f"{' '.join(command)}\n{detail}"
        )
        self.returncode = returncode


class AcpxClient:
    def __init__(self, cwd):
        self.cwd = Path(cwd)

    def _run_setup(self, args, timeout=30):
        command = ["acpx", "--approve-all", "openclaw", *args]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=self.cwd,
            env={**os.environ},
        )
        if result.returncode != 0:
            raise AcpxCommandError(command, result.returncode, result.stderr)
        return result

    def new_session(self):
        return self._run_setup(["sessions", "new"])

    def ensure_session(self):
        return self._run_setup(["sessions", "ensure"])

    def set_elevated(self):
        return self._run_setup(["prompt", "/elevated full"])

    def prompt(self, prompt, timeout=600):
        command = [
            "acpx",
            "--approve-all",
            "--format",
            "json",
            "openclaw",
            "prompt",
            prompt,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=self.cwd,
            env={**os.environ},
        )
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        return result.stdout, result.returncode
