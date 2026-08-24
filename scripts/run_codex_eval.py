#!/usr/bin/env python3
"""Two-phase Codex CLI evaluation: task process plus verifier process."""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_runtime_helpers import (
    classify_evaluator_failure,
    collect_web_runtime_diagnostics,
    create_case_workspace,
    downgrade_browser_infrastructure_failure,
    e2e_task_requirements,
    extract_codex_task_runtime_evidence,
    find_judgment_json,
    redact_sensitive_text,
    seed_agora_credentials,
    start_nextjs_verification_server,
    stop_verification_server,
    verification_instructions,
)

RUN_DIR = Path(os.environ["RUN_DIR"])
CASES = json.loads(Path("/tmp/codex-eval-cases.json").read_text())
REPO_ROOT = Path.cwd()


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def run_codex(prompt, workspace, output_path, timeout):
    output_path = output_path.resolve()
    command = [
        "codex", "exec", "--json", "--skip-git-repo-check",
        "--sandbox", "danger-full-access", "--output-last-message", str(output_path),
    ]
    output_path.unlink(missing_ok=True)
    logs = []
    for _ in range(2):
        try:
            result = subprocess.run(
                command, input=prompt, capture_output=True, text=True,
                timeout=timeout, cwd=workspace,
            )
        except subprocess.TimeoutExpired:
            return "", -1, f"TIMEOUT after {timeout}s"
        raw = result.stdout + "\n" + result.stderr
        logs.append(raw)
        if result.returncode == 0 or not (
            "stream disconnected" in raw.lower()
            or "stream closed before response.completed" in raw.lower()
        ):
            answer = output_path.read_text(errors="replace") if output_path.exists() else ""
            return answer, result.returncode, "\n".join(logs)
        output_path.unlink(missing_ok=True)
    return "", 1, "\n".join(logs)


def build_task_prompt(case, workspace, credentials):
    return (
        f"You are working in workspace: {workspace}\n\n"
        f"First read {workspace}/.agents/skills/agora/SKILL.md, then follow its routing instructions.\n\n"
        f"Task: answer this user request naturally, using the workspace as needed:\n{case['user_prompt']}\n\n"
        "Requirements:\n"
        f"- Treat {workspace} as your only workspace.\n"
        "- Keep all file reads, writes, and shell commands inside it.\n"
        f"{e2e_task_requirements(workspace, credentials)}"
        "- Give the exact answer you would send to the user."
    )


def build_verifier_prompt(
    case, workspace, answer, assertions, verification, diagnostics, task_facts, server
):
    return (
        "You are an independent evaluator judging another fresh Codex task process.\n"
        "Inspect the workspace and run verification commands before judging.\n\n"
        f"Task prompt:\n{case['user_prompt']}\n\n"
        f"Task answer:\n{answer[:4000]}\n\n"
        f"Workspace: {workspace}\n"
        f"Runner diagnostics: {json.dumps(diagnostics)}\n\n"
        f"Task process facts: {json.dumps(task_facts)}\n"
        f"Verification-server facts: {json.dumps(server)}\n\n"
        "Verify the workspace before judging:\n"
        "- The runner may launch a verification-only server after the task exits; it can prove browser behavior but cannot alone prove the task agent started the server. Use Task process facts for that assertion.\n"
        "- Treat unavailable evidence as blocked rather than inferring pass.\n\n"
        f"Required verification actions:\n{verification}\n\n"
        f"Assertions:\n{assertions}\n\n"
        "Return only JSON with status, assertions, and notes."
    )


for case in CASES:
    case_id = case["case_id"]
    workspace_parent = Path(f"/tmp/codex-eval-{case_id}")
    workspace_parent.mkdir(parents=True, exist_ok=True)
    workspace, _ = create_case_workspace(
        REPO_ROOT, workspace_parent, case_id, os.environ.get("TARGET_ID", "agora")
    )
    credentials = seed_agora_credentials(workspace)
    artifact_dir = RUN_DIR / "case-artifacts" / case_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    task_started = now()
    task_answer_path = artifact_dir / "final-answer.txt"
    task_answer, task_exit, task_raw = run_codex(
        build_task_prompt(case, workspace, credentials), workspace, task_answer_path, 900
    )
    task_completed = now()
    safe_task_answer = redact_sensitive_text(task_answer)
    safe_task_raw = redact_sensitive_text(task_raw)
    task_facts = extract_codex_task_runtime_evidence(safe_task_raw)
    task_answer_path.write_text(safe_task_answer + "\n")
    (artifact_dir / "task-agent-raw.jsonl").write_text(safe_task_raw)
    (artifact_dir / "task-agent-diagnostics.json").write_text(json.dumps({
        "exit_code": task_exit, "raw_bytes": len(safe_task_raw.encode()),
    }, indent=2) + "\n")

    verification_server, server_facts = start_nextjs_verification_server(
        workspace, artifact_dir
    )
    diagnostics, runtime_logs = collect_web_runtime_diagnostics(workspace)
    (artifact_dir / "runtime-diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
    for name, content in runtime_logs.items():
        (artifact_dir / name).write_text(content)
    workspace_files = subprocess.run(
        ["find", workspace, "-type", "f", "-maxdepth", "4"],
        capture_output=True, text=True,
    ).stdout
    case_data = yaml.safe_load(Path(case["path"]).read_text())
    assertions = json.dumps(case_data.get("assert", {}).get("required", []), indent=2)
    verification = verification_instructions(case_data)

    verification_started = now()
    verifier_output = artifact_dir / "evaluator-last-message.txt"
    verifier_answer, verifier_exit, verifier_raw = run_codex(
        build_verifier_prompt(
            case,
            workspace,
            safe_task_answer,
            assertions,
            verification,
            diagnostics,
            task_facts,
            server_facts,
        ),
        workspace, verifier_output, 300,
    )
    verification_completed = now()
    safe_verifier_answer = redact_sensitive_text(verifier_answer)
    safe_verifier_raw = redact_sensitive_text(verifier_raw)
    (artifact_dir / "evaluator-raw.jsonl").write_text(safe_verifier_raw)

    stop_verification_server(verification_server)

    blocked_reason, failure_note = classify_evaluator_failure(verifier_exit, safe_verifier_answer)
    result = {
        "case_id": case_id,
        "workspace_root": workspace,
        "thread_id": None,
        "session_path": "case-artifacts/%s/task-agent-raw.jsonl" % case_id,
        "status": "blocked",
        "blocked_reason": blocked_reason,
        "assertions": [],
        "notes": [failure_note],
        "suggested_fix_files": case_data.get("notes", {}).get("likely_fix_files", []),
        "task_started_at": task_started.isoformat(),
        "task_completed_at": task_completed.isoformat(),
        "task_duration_s": round((task_completed - task_started).total_seconds()),
        "verification_started_at": verification_started.isoformat(),
        "verification_completed_at": verification_completed.isoformat(),
        "verification_duration_s": round((verification_completed - verification_started).total_seconds()),
        "total_duration_s": round((verification_completed - task_started).total_seconds()),
    }
    judgment = find_judgment_json(safe_verifier_answer) if verifier_exit == 0 else None
    if judgment:
        judgment, browser_blocked = downgrade_browser_infrastructure_failure(
            judgment, safe_verifier_answer + "\n" + safe_verifier_raw
        )
        status = str(judgment.get("status", "blocked")).lower()
        result.update({
            "status": status if status in {"pass", "fail", "blocked"} else "blocked",
            "blocked_reason": "environment" if browser_blocked else None,
            "assertions": judgment.get("assertions", []),
            "notes": judgment.get("notes", []),
        })

    evidence = {
        "task_agent_output": safe_task_answer[:50000],
        "task_agent_raw": safe_task_raw[:50000],
        "task_agent_exit_code": task_exit,
        "task_runtime_facts": task_facts,
        "verification_server": server_facts,
        "evaluator_output": safe_verifier_answer[:50000],
        "evaluator_raw": safe_verifier_raw[:50000],
        "workspace_files": workspace_files,
        "runtime_diagnostics": diagnostics,
    }
    (artifact_dir / "accepted-session.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    (RUN_DIR / "case-results" / f"{case_id}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    with (RUN_DIR / "transcript.md").open("a") as transcript:
        transcript.write(f"## {case_id}\n\n{safe_task_answer}\n\n")
    print(f"{case_id}: {result['status']}", flush=True)
