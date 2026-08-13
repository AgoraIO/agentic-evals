#!/usr/bin/env python3
"""Two-phase Hermes Agent evaluation: task agent + Codex evaluator."""
import json, subprocess, os, datetime, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_runtime_helpers import (
    collect_web_runtime_diagnostics,
    create_case_workspace,
    e2e_task_requirements,
    hermes_env,
    redact_sensitive_text,
    seed_agora_credentials,
)

sys.stdout.reconfigure(line_buffering=True)

print("=== Hermes eval script starting ===", flush=True)

try:
    import yaml
except ImportError:
    print("pyyaml not installed, installing...", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

run_dir = Path(os.environ["RUN_DIR"])
print(f"RUN_DIR: {run_dir}", flush=True)

cases_file = Path("/tmp/hermes-eval-cases.json")
if not cases_file.exists():
    print(f"ERROR: {cases_file} not found!", flush=True)
    sys.exit(1)
cases = json.loads(cases_file.read_text())
print(f"Cases: {len(cases)}", flush=True)

repo_root = Path.cwd()
model_flag = os.environ.get("HERMES_MODEL", "")
print(f"repo_root: {repo_root}", flush=True)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def run_hermes(prompt, timeout=600, label="agent", cwd=None):
    """Run a prompt via hermes chat -q (one-shot, non-interactive)."""
    cmd = ["hermes", "chat", "--yolo", "--quiet", "-q", prompt]
    if model_flag:
        cmd.extend(["--model", model_flag])
    print(f"  [{label}] Running hermes chat -q ... (cwd={cwd})")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            env=hermes_env(), cwd=cwd
        )
        return result.stdout, result.returncode, result.stderr
    except subprocess.TimeoutExpired:
        print(f"  [{label}] TIMEOUT after {timeout}s")
        return "", -1, f"TIMEOUT after {timeout}s"


def run_evaluator(prompt, timeout=300):
    """Run evaluator via Codex CLI."""
    codex_home = Path.home() / ".codex"
    codex_home.mkdir(exist_ok=True)
    endpoint = os.environ.get("RESPONSES_API_ENDPOINT", "")
    if endpoint:
        base_url = endpoint.replace("/responses", "").rstrip("/")
        config = (
            'model_provider = "OpenAI"\n'
            'model = "gpt-5.4"\n'
            'disable_response_storage = true\n'
            '\n'
            '[model_providers.OpenAI]\n'
            'name = "OpenAI"\n'
            f'base_url = "{base_url}"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n'
        )
        (codex_home / "config.toml").write_text(config)
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            auth = json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": api_key})
            (codex_home / "auth.json").write_text(auth)

    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "danger-full-access",
           "--output-last-message", "/tmp/codex-eval-output.md"]
    print(f"  [eval] Running codex exec for judgment...")
    try:
        result = subprocess.run(
            cmd, input=prompt, stdout=subprocess.PIPE, stderr=None,
            text=True, timeout=timeout
        )
        output_path = Path("/tmp/codex-eval-output.md")
        if output_path.exists():
            return output_path.read_text(), result.returncode
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        print(f"  [eval] TIMEOUT after {timeout}s")
        return "", -1


for case in cases:
    cid = case["case_id"]
    print(f"\n{'='*60}")
    print(f"Case: {cid}")
    print(f"{'='*60}")

    # Create workspace
    ws = Path(f"/tmp/hermes-eval-{cid}")
    ws.mkdir(parents=True, exist_ok=True)
    attempt_ws, _ = create_case_workspace(
        repo_root, ws, cid, os.environ.get("TARGET_ID", "agora")
    )
    cred_path = seed_agora_credentials(attempt_ws)
    print(f"Workspace: {attempt_ws}")

    # --- Phase 1: Task Agent (Hermes) ---
    t1_start = now()
    print(f"\n--- Phase 1: Task Agent / Hermes ({t1_start.isoformat()}) ---", flush=True)

    task_prompt = (
        f"You are working in workspace: {attempt_ws}\n\n"
        f"IMPORTANT: Before starting, read the skill documentation files in your workspace:\n"
        f"  1. First read: {attempt_ws}/.agents/skills/agora/SKILL.md\n"
        f"  2. Then follow its routing instructions to find the right product reference.\n"
        f"These files contain critical guidance for completing the task correctly.\n\n"
        f"Task: answer this user request naturally, using the workspace as needed:\n"
        f'"{case["user_prompt"]}"\n\n'
        f"Requirements:\n"
        f"- Treat {attempt_ws} as your only workspace.\n"
        f"- Keep all file reads, writes, and shell commands inside it.\n"
        f"{e2e_task_requirements(attempt_ws, cred_path)}"
        f"- Give the exact answer you would send to the user."
    )

    task_stdout, task_exit, task_stderr = run_hermes(task_prompt, timeout=600, label="task", cwd=attempt_ws)
    t1_end = now()
    t1_dur = (t1_end - t1_start).total_seconds()
    print(f"Phase 1 completed in {t1_dur:.0f}s (exit={task_exit})")

    art_dir = run_dir / "case-artifacts" / cid
    art_dir.mkdir(parents=True, exist_ok=True)
    safe_task_stdout = redact_sensitive_text(task_stdout)
    safe_task_stderr = redact_sensitive_text(task_stderr or "")
    (art_dir / "task-agent-raw.txt").write_text(safe_task_stdout)
    if safe_task_stderr:
        (art_dir / "task-agent-stderr.txt").write_text(safe_task_stderr)

    task_response = safe_task_stdout
    print(f"Phase 1 response (first 500):\n{task_response[:500]}")
    (art_dir / "final-answer.txt").write_text(task_response + "\n")

    runtime_diagnostics, runtime_logs = collect_web_runtime_diagnostics(attempt_ws)
    (art_dir / "runtime-diagnostics.json").write_text(
        json.dumps(runtime_diagnostics, indent=2) + "\n"
    )
    for log_name, log_text in runtime_logs.items():
        (art_dir / log_name).write_text(log_text)
    print(
        "Runtime diagnostics: "
        + json.dumps(runtime_diagnostics, ensure_ascii=False)
    )

    # Workspace state
    ws_files = subprocess.run(
        ["find", attempt_ws, "-type", "f", "-maxdepth", "4"],
        capture_output=True, text=True).stdout
    print(f"Workspace files ({ws_files.count(chr(10))} files):\n{ws_files[:500]}")

    # --- Phase 2: Evaluator Agent (Codex) ---
    t2_start = now()
    print(f"\n--- Phase 2: Evaluator ({t2_start.isoformat()}) ---")

    case_data = yaml.safe_load(open(case["path"]))
    assertions_text = json.dumps(case_data.get("assert", {}).get("required", []), indent=2)

    eval_prompt = (
        f"Please analyze this agent's work and give me your judgment.\n\n"
        f"The agent was asked to: {case['user_prompt'][:300]}\n\n"
        f"The agent responded:\n{task_response[:1500]}\n\n"
        f"The agent's workspace is at: {attempt_ws}\n"
        f"Files in workspace: {ws_files.count(chr(10))}\n\n"
        f"Runner-collected runtime diagnostics:\n{json.dumps(runtime_diagnostics, indent=2)}\n\n"
        f"IMPORTANT: Verify by inspecting the workspace directly:\n"
        f"- Check if {attempt_ws}/agent-quickstart-nextjs exists (git clone evidence)\n"
        f"- Check if a .env.local file exists with Agora credentials\n"
        f"- Use runtime-diagnostics.json and the saved install/dev logs as primary runtime evidence.\n"
        f"- For browser assertions, invoke the installed agent-browser CLI through shell commands.\n"
        f"- Open http://localhost:3000, activate the Start Conversation button, and inspect the resulting page state.\n"
        f"- Inspect agent-browser network requests for /api/invite-agent; do not infer Invite success from the landing-page GET alone.\n"
        f"- A listening process or successful HEAD request is not enough: require a successful GET with a non-empty body.\n"
        f"- Run these checks yourself before judging.\n\n"
        f"Check these assertions and tell me pass or fail for each:\n{assertions_text}\n\n"
        f"Write your answer as a JSON object with this structure:\n"
        '{"case_id":"' + cid + '","status":"pass or fail",'
        '"assertions":[{"summary":"description","status":"pass or fail","evidence":["what you observed"]}],'
        '"notes":["any observations"]}\n\n'
        "Please run the verification commands and write the JSON now."
    )

    eval_response, eval_exit = run_evaluator(eval_prompt)
    t2_end = now()
    t2_dur = (t2_end - t2_start).total_seconds()
    print(f"Phase 2 completed in {t2_dur:.0f}s (exit={eval_exit})")

    safe_eval_response = redact_sensitive_text(eval_response)
    (art_dir / "evaluator-raw.txt").write_text(safe_eval_response)
    print(f"Phase 2 response (first 800):\n{safe_eval_response[:800]}")

    # Parse judgment
    case_result = {
        "case_id": cid,
        "status": "blocked",
        "blocked_reason": "evaluator-parse-error",
        "assertions": [],
        "notes": ["Could not parse evaluator response"],
        "task_started_at": t1_start.isoformat(),
        "task_completed_at": t1_end.isoformat(),
        "task_duration_s": round(t1_dur),
        "verification_started_at": t2_start.isoformat(),
        "verification_completed_at": t2_end.isoformat(),
        "verification_duration_s": round(t2_dur),
        "total_duration_s": round(t1_dur + t2_dur),
        "workspace_root": attempt_ws,
    }

    json_match = re.search(r'\{[\s\S]*\}', safe_eval_response)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            case_result.update({
                "status": parsed.get("status", "blocked"),
                "assertions": parsed.get("assertions", []),
                "notes": parsed.get("notes", []),
                "blocked_reason": None,
            })
        except Exception as e:
            print(f"Judgment parse error: {e}")

    safe_case_result = redact_sensitive_text(json.dumps(case_result, indent=2))
    (run_dir / "case-results" / f"{cid}.json").write_text(
        safe_case_result + "\n"
    )

    # Evidence bundle
    evidence = {
        "task_agent_output": safe_task_stdout[:50000],
        "task_agent_stderr": safe_task_stderr[:10000],
        "evaluator_output": safe_eval_response[:50000],
        "workspace_files": ws_files,
        "runtime_diagnostics": runtime_diagnostics,
    }
    (art_dir / "accepted-session.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")

    print(f"\n--- Result: {case_result['status']} ---")
    for a in case_result.get("assertions", []):
        print(f"  [{a.get('status','?')}] {a.get('summary','')[:100]}")
    for n in case_result.get("notes", []):
        print(f"  note: {n[:200]}")

print("\nAll cases complete.")
