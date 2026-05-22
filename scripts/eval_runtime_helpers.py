#!/usr/bin/env python3
"""Shared helpers for two-phase eval runtime scripts."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def resolve_source_workspace(repo_root: Path) -> Path:
    """Return source_workspace for create_case_workspace.sh (either layout)."""
    parent = repo_root.parent
    if (parent / "agentic-evals" / "targets").is_dir():
        return parent
    return repo_root


def create_case_workspace(
    repo_root: Path,
    ws_root: Path,
    case_id: str,
    target_id: str | None = None,
) -> tuple[str, bool]:
    """Create isolated case workspace. Returns (attempt_ws, script_ok)."""
    target_id = target_id or os.environ.get("TARGET_ID", "agora")
    source_ws = resolve_source_workspace(repo_root)
    script = repo_root / ".agents/skills/skills-evaluation/scripts/create_case_workspace.sh"
    result = subprocess.run(
        ["bash", str(script), str(source_ws), str(ws_root), case_id, "--target", target_id],
        capture_output=True,
        text=True,
    )
    attempt_ws = (
        result.stdout.strip().split("\n")[-1] if result.stdout.strip() else str(ws_root)
    )
    if result.returncode != 0:
        print(f"Workspace script failed (exit={result.returncode})")
        print(f"  stdout: {result.stdout[:500]}")
        print(f"  stderr: {result.stderr[:500]}")
        attempt_ws = fallback_workspace(repo_root, ws_root, case_id, target_id)
        return attempt_ws, False
    return attempt_ws, True


def fallback_workspace(
    repo_root: Path, ws_root: Path, case_id: str, target_id: str
) -> str:
    """Copy only the target skill tree when create_case_workspace.sh fails."""
    safe_case_id = case_id.replace("/", "-")
    attempt_ws = ws_root / safe_case_id / "attempt-01"
    attempt_ws.mkdir(parents=True, exist_ok=True)
    src_skill = repo_root / ".agents" / "skills" / target_id
    dst_skill = attempt_ws / ".agents" / "skills" / target_id
    if src_skill.is_dir():
        dst_skill.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-rL", str(src_skill), str(dst_skill)], capture_output=True)
        copied = subprocess.run(
            ["find", str(dst_skill), "-type", "f"], capture_output=True, text=True
        )
        print(f"Fallback: copied {copied.stdout.count(chr(10))} files to {dst_skill}")
    return str(attempt_ws)


# Next.js quickstart env keys (see agora skill references/cli/env.md)
NEXTJS_APP_ID_KEY = "NEXT_PUBLIC_AGORA_APP_ID"
NEXTJS_APP_CERT_KEY = "NEXT_AGORA_APP_CERTIFICATE"
CI_APP_ID_KEY = "AGORA_APP_ID"
CI_APP_CERT_KEY = "AGORA_APP_CERTIFICATE"


def seed_agora_credentials(attempt_ws: str | Path) -> Path | None:
    """Write literal Agora creds into the case workspace for agent runtimes."""
    app_id = os.environ.get(CI_APP_ID_KEY, "")
    app_cert = os.environ.get(CI_APP_CERT_KEY, "")
    if not app_id or not app_cert:
        print(
            f"warning: {CI_APP_ID_KEY} or {CI_APP_CERT_KEY} not set; skipping credential seed"
        )
        return None
    cred_path = Path(attempt_ws) / ".agora-ci-credentials.env"
    cred_path.write_text(
        f"{CI_APP_ID_KEY}={app_id}\n"
        f"{CI_APP_CERT_KEY}={app_cert}\n"
        f"{NEXTJS_APP_ID_KEY}={app_id}\n"
        f"{NEXTJS_APP_CERT_KEY}={app_cert}\n"
    )
    cred_path.chmod(0o600)
    return cred_path


def e2e_task_requirements(attempt_ws: str | Path, cred_path: Path | None) -> str:
    """Common E2E task requirements for ConvoAI quickstart cases."""
    cred_file = cred_path or Path(attempt_ws) / ".agora-ci-credentials.env"
    return (
        f"- Read Agora credentials from {cred_file}. CI provides {CI_APP_ID_KEY} and "
        f"{CI_APP_CERT_KEY}; the official Next.js quickstart expects different keys in "
        f"`.env.local`: {NEXTJS_APP_ID_KEY} and {NEXTJS_APP_CERT_KEY} (same literal values).\n"
        f"- When writing the Next.js quickstart `.env.local`, use {NEXTJS_APP_ID_KEY} and "
        f"{NEXTJS_APP_CERT_KEY} with resolved literal values from the credentials file — "
        f"do NOT copy {CI_APP_ID_KEY}/{CI_APP_CERT_KEY} key names into `.env.local`, and "
        f"do NOT write shell variable syntax like ${{{CI_APP_ID_KEY}}} into files.\n"
        f"- If git clone over HTTPS fails, use tarball download instead: "
        f"curl -L https://github.com/OWNER/REPO/archive/refs/heads/main.tar.gz | tar xz\n"
        f"- When starting a dev server (e.g. npm run dev, pnpm dev), you MUST launch it as a "
        f"background process (e.g. `nohup pnpm dev > /dev/null 2>&1 &`) so it keeps running "
        f"after you finish.\n"
        f"- If `pnpm install` exits with only `[ERR_PNPM_IGNORED_BUILDS]`, treat install as "
        f"complete and continue to `pnpm dev`.\n"
        f"- After starting the server, verify it is listening (e.g. curl -I http://localhost:3000) "
        f"before reporting success.\n"
    )


def hermes_env() -> dict[str, str]:
    """Environment for hermes subprocess with PATH and Agora creds."""
    env = {**os.environ}
    home_local = Path.home() / ".local" / "bin"
    env["PATH"] = f"{home_local}{os.pathsep}{env.get('PATH', '')}"
    return env
