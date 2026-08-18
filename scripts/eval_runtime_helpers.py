#!/usr/bin/env python3
"""Shared helpers for two-phase eval runtime scripts."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from json import JSONDecoder
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

SENSITIVE_ENV_KEYS = (
    CI_APP_ID_KEY,
    CI_APP_CERT_KEY,
    NEXTJS_APP_ID_KEY,
    NEXTJS_APP_CERT_KEY,
)


def redact_sensitive_text(text: str) -> str:
    """Remove Agora credential values before text is written to run artifacts."""
    redacted = text
    assignment_pattern = re.compile(
        rf"(?m)(\b(?:{'|'.join(SENSITIVE_ENV_KEYS)})\s*=\s*)[^\s\"']+"
    )
    redacted = assignment_pattern.sub(r"\1[REDACTED]", redacted)
    sensitive_values = sorted(
        {os.environ.get(key, "") for key in SENSITIVE_ENV_KEYS} - {""},
        key=len,
        reverse=True,
    )
    for value in sensitive_values:
        redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def find_judgment_json(text: str) -> dict[str, object] | None:
    """Return the last JSON judgment object embedded in evaluator output."""
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", text or "").strip()
    if not cleaned:
        return None

    fenced = re.findall(
        r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE
    )
    candidates = [*reversed(fenced), cleaned]
    decoder = JSONDecoder()
    for candidate in candidates:
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and {"status", "assertions"} <= parsed.keys():
                return parsed
    return None


def classify_evaluator_failure(exit_code: int, output: str) -> tuple[str, str]:
    """Classify evaluator failures before attempting result JSON parsing."""
    if exit_code != 0:
        return "evaluator-execution-error", f"Evaluator exited with code {exit_code}."
    if not output.strip():
        return "evaluator-empty-output", "Evaluator completed without a final response."
    return "evaluator-parse-error", "Evaluator response did not contain a valid judgment JSON object."


def extract_openclaw_command_evidence(raw_json: str) -> list[str]:
    """Return completed shell commands from OpenClaw ACP event history."""
    pending: dict[str, str] = {}
    completed: list[str] = []
    for line in raw_json.splitlines():
        try:
            update = json.loads(line).get("params", {}).get("update", {})
        except json.JSONDecodeError:
            continue
        event_type = update.get("sessionUpdate")
        call_id = update.get("toolCallId", "")
        raw_input = update.get("rawInput", {})
        command = raw_input.get("command") if isinstance(raw_input, dict) else None
        if event_type == "tool_call" and call_id and isinstance(command, str):
            pending[call_id] = command
        elif event_type == "tool_call_update" and update.get("status") == "completed":
            command = pending.pop(call_id, None)
            if command:
                completed.append(command)
    return list(dict.fromkeys(completed))


_BROWSER_RUNTIME_MARKERS = (
    "failed to connect:",
    "daemon may be busy or unresponsive",
    "could not start daemon",
    "socket directory",
)


def browser_verification_unavailable(text: str) -> bool:
    """Recognize agent-browser infrastructure failures, not page failures."""
    lowered = (text or "").lower()
    return "agent-browser" in lowered and any(
        marker in lowered for marker in _BROWSER_RUNTIME_MARKERS
    )


def downgrade_browser_infrastructure_failure(
    judgment: dict[str, object], diagnostics: str
) -> tuple[dict[str, object], bool]:
    """Convert browser-only false failures to blocked when the CLI was unavailable."""
    if not browser_verification_unavailable(diagnostics):
        return judgment, False

    assertions = judgment.get("assertions")
    if not isinstance(assertions, list):
        return judgment, False

    changed = False
    for assertion in assertions:
        if not isinstance(assertion, dict) or assertion.get("status") != "fail":
            continue
        summary = str(assertion.get("summary", "")).lower()
        if "browser" in summary or "page loads" in summary:
            assertion["status"] = "blocked"
            evidence = assertion.setdefault("evidence", [])
            if isinstance(evidence, list):
                evidence.append(
                    "agent-browser infrastructure was unavailable; this does not establish a demo failure."
                )
            changed = True

    if changed and not any(
        isinstance(assertion, dict) and assertion.get("status") == "fail"
        for assertion in assertions
    ):
        judgment["status"] = "blocked"
        notes = judgment.setdefault("notes", [])
        if isinstance(notes, list):
            notes.append(
                "Browser verification was blocked by agent-browser infrastructure, not judged as a demo failure."
            )
    return judgment, changed


def probe_http_endpoint(url: str, timeout: int = 10) -> dict[str, object]:
    """Probe an endpoint without persisting its potentially sensitive response body."""
    started = time.monotonic()
    result: dict[str, object] = {
        "url": url,
        "status": None,
        "body_bytes": 0,
        "error": None,
    }
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(1_000_001)
            result["status"] = response.status
            result["body_bytes"] = len(body)
            result["body_truncated"] = len(body) > 1_000_000
    except urllib.error.HTTPError as error:
        result["status"] = error.code
        result["error"] = f"HTTP {error.code}"
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    return result


def _find_nextjs_app(workspace: Path) -> Path | None:
    for package_json in workspace.rglob("package.json"):
        if "node_modules" in package_json.parts:
            continue
        try:
            package = json.loads(package_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if package.get("name") == "convoai-quickstart-web-nextjs":
            return package_json.parent
    return None


def _denied_build_scripts(app_dir: Path) -> tuple[list[str], str | None]:
    policy_path = app_dir / "pnpm-workspace.yaml"
    if not policy_path.exists():
        return [], None
    try:
        import yaml

        policy = yaml.safe_load(policy_path.read_text()) or {}
        allow_builds = policy.get("allowBuilds", {})
        if not isinstance(allow_builds, dict):
            return [], "allowBuilds is not a mapping"
        return sorted(name for name, allowed in allow_builds.items() if allowed is False), None
    except ModuleNotFoundError:
        denied = []
        in_allow_builds = False
        for line in policy_path.read_text().splitlines():
            if line.strip() == "allowBuilds:":
                in_allow_builds = True
                continue
            if in_allow_builds and line and not line[0].isspace():
                break
            match = re.match(r"^\s+([^:#]+):\s*false\s*$", line)
            if in_allow_builds and match:
                denied.append(match.group(1).strip())
        return sorted(denied), None
    except Exception as error:
        return [], f"{type(error).__name__}: {error}"


def collect_web_runtime_diagnostics(
    workspace: str | Path,
) -> tuple[dict[str, object], dict[str, str]]:
    """Collect bounded, redacted diagnostics for the Next.js E2E quickstart."""
    workspace = Path(workspace)
    app_dir = _find_nextjs_app(workspace)
    if app_dir is None:
        return {"app_dir": None, "error": "quickstart app not found"}, {}

    denied_build_scripts, build_policy_error = _denied_build_scripts(app_dir)
    diagnostics: dict[str, object] = {
        "app_dir": str(app_dir.relative_to(workspace)),
        "denied_build_scripts": denied_build_scripts,
        "build_policy_error": build_policy_error,
        "probes": [
            probe_http_endpoint("http://localhost:3000/"),
        ],
    }
    home_probe = diagnostics["probes"][0]
    diagnostics["page_ready"] = (
        home_probe["error"] is None
        and isinstance(home_probe["status"], int)
        and 200 <= home_probe["status"] < 400
        and home_probe["body_bytes"] > 0
    )

    try:
        listener = subprocess.run(
            ["lsof", "-n", "-P", "-iTCP:3000", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        diagnostics["port_3000_listener"] = redact_sensitive_text(
            (listener.stdout or listener.stderr).strip()
        )
        diagnostics["listener_error"] = None
    except OSError as error:
        diagnostics["port_3000_listener"] = ""
        diagnostics["listener_error"] = f"{type(error).__name__}: {error}"

    logs: dict[str, str] = {}
    for name in ("install.log", "dev-server.log"):
        log_path = app_dir / ".eval" / name
        if log_path.exists():
            logs[name] = redact_sensitive_text(
                log_path.read_text(errors="replace")[-100_000:]
            )
    return diagnostics, logs


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
        "- Follow the ConvoAI skill flow in this workspace (especially quickstart guidance).\n"
        "- For this case, use the official Next.js quickstart repository only: "
        "`https://github.com/AgoraIO-Conversational-AI/agent-quickstart-nextjs`.\n"
        f"- Read credentials from `{cred_file}`; the key mapping and `.env.local` write pattern come from the ConvoAI quickstart guidance in this skill.\n"
        "- Verify readiness with a real GET request that returns a non-empty body; a listening port or successful HEAD request alone is insufficient.\n"
        "- This is an automated CI evaluation: proceed without confirmation prompts.\n"
    )


def hermes_env() -> dict[str, str]:
    """Environment for hermes subprocess with PATH and Agora creds."""
    env = {**os.environ}
    home_local = Path.home() / ".local" / "bin"
    env["PATH"] = f"{home_local}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
    return env
