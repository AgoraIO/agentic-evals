#!/usr/bin/env python3
"""Two-phase OpenClaw evaluation via acpx: task agent + evaluator agent."""
import json, subprocess, os, datetime, re, sys, time
from pathlib import Path
from json import JSONDecoder

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_runtime_helpers import (
    create_case_workspace,
    e2e_task_requirements,
    seed_agora_credentials,
)

# Force unbuffered output so prints appear in CI logs
sys.stdout.reconfigure(line_buffering=True)

print("=== OpenClaw eval script starting ===", flush=True)

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed, installing...", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

run_dir = Path(os.environ["RUN_DIR"])
print(f"RUN_DIR: {run_dir}", flush=True)

cases_file = Path("/tmp/eval-cases.json")
if not cases_file.exists():
    print(f"ERROR: {cases_file} not found!", flush=True)
    sys.exit(1)
cases = json.loads(cases_file.read_text())
print(f"Cases: {len(cases)}", flush=True)

repo_root = Path.cwd()
print(f"repo_root: {repo_root}", flush=True)

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def run_openclaw(prompt, timeout=600, label="agent"):
    """Run a prompt via acpx openclaw with persistent session for full tool access."""
    print(f"  [{label}] Creating new session and sending prompt...")
    
    # Step 1: Ensure a session exists
    subprocess.run(
        ["acpx", "--approve-all", "openclaw", "sessions", "ensure"],
        capture_output=True, text=True, timeout=30
    )
    
    # Step 2: Send prompt to the session (not exec)
    cmd = ["acpx", "--approve-all", "--format", "json", "openclaw", "prompt", prompt]
    try:
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=None,
            text=True, timeout=timeout,
            env={**os.environ}
        )
        return result.stdout, result.returncode
    except subprocess.TimeoutExpired:
        print(f"  [{label}] TIMEOUT after {timeout}s")
        return json.dumps({"error": f"TIMEOUT after {timeout}s"}), -1

def run_evaluator(prompt, timeout=300):
    """Run evaluator via Codex CLI with custom API endpoint."""
    # Write Codex config to use the same gateway as OpenClaw
    codex_home = Path.home() / ".codex"
    codex_home.mkdir(exist_ok=True)
    endpoint = os.environ.get("RESPONSES_API_ENDPOINT", "")
    if endpoint:
        # Codex appends /responses to base_url, so we need base_url to end with /v1
        # RESPONSES_API_ENDPOINT = http://host:port/v1/responses
        # base_url should be = http://host:port/v1
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
        # Also write auth.json so Codex has the API key
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

def extract_response_text(raw_json):
    """Extract the agent's text response from acpx NDJSON output."""
    text_parts = []
    for line in raw_json.strip().split("\n"):
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            # Check for agent_message_chunk in session/update
            params = msg.get("params", {})
            update = params.get("update", {})
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content", {})
                if content.get("type") == "text":
                    text_parts.append(content.get("text", ""))
            # Also check for direct result with text (some ACP responses)
            result = msg.get("result", {})
            if isinstance(result, dict) and result.get("text"):
                text_parts.append(result["text"])
        except:
            continue
    return "".join(text_parts)

def extract_tool_calls(raw_json):
    """Extract tool call info from acpx NDJSON output."""
    tools = []
    for line in raw_json.strip().split("\n"):
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            params = msg.get("params", {})
            update = params.get("update", {})
            su = update.get("sessionUpdate", "")
            # OpenClaw uses various tool-related session updates
            if su in ("tool_call_start", "tool_call", "tool_use_start",
                       "tool_use", "tool_result", "tool_output"):
                tools.append({"type": su, "data": update})
        except:
            continue
    return tools

def count_ndjson_events(raw_json):
    """Count total NDJSON lines for diagnostics."""
    return sum(1 for line in raw_json.strip().split("\n") if line.strip())


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")


def find_judgment_json(text):
    cleaned = strip_ansi(text).strip()
    if not cleaned:
        return None

    fence_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    for block in reversed(fence_matches):
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict) and ("status" in parsed or "assertions" in parsed):
                return parsed
        except Exception:
            pass

    decoder = JSONDecoder()
    for i, ch in enumerate(cleaned):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned[i:])
            if isinstance(obj, dict) and ("status" in obj or "assertions" in obj):
                return obj
        except Exception:
            continue
    return None

for case in cases:
    cid = case["case_id"]
    print(f"\n{'='*60}")
    print(f"Case: {cid}")
    print(f"{'='*60}")

    # Create workspace
    ws = Path(f"/tmp/openclaw-eval-{cid}")
    ws.mkdir(parents=True, exist_ok=True)
    print(f"repo_root: {repo_root}")
    attempt_ws, script_ok = create_case_workspace(
        repo_root, ws, cid, os.environ.get("TARGET_ID", "agora")
    )
    cred_path = seed_agora_credentials(attempt_ws)
    if script_ok:
        qs = Path(attempt_ws) / ".agents/skills/agora/references/conversational-ai/quickstarts.md"
        print(f"quickstarts.md in workspace: {qs.exists()}")
    print(f"Workspace: {attempt_ws}")

    # --- Phase 1: Task Agent ---
    # Reset session for clean state and enable elevated mode
    subprocess.run(
        ["acpx", "--approve-all", "openclaw", "sessions", "new"],
        capture_output=True, text=True, timeout=30
    )
    time.sleep(3)
    # Enable auto-approve for shell commands
    subprocess.run(
        ["acpx", "--approve-all", "openclaw", "prompt", "/elevated full"],
        capture_output=True, text=True, timeout=30
    )
    time.sleep(2)
    print("  Elevated mode set to full (auto-approve)", flush=True)

    t1_start = now()
    print(f"\n--- Phase 1: Task Agent ({t1_start.isoformat()}) ---", flush=True)

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

    task_raw, task_exit = run_openclaw(task_prompt, timeout=600, label="task")

    # Retry up to 2 more times if the agent times out or produces no output
    MAX_RETRIES = 3
    for attempt in range(2, MAX_RETRIES + 1):
        task_response_check = extract_response_text(task_raw)
        is_timeout = '"error"' in task_raw and "TIMEOUT" in task_raw
        is_empty = not task_response_check.strip()
        if not is_timeout and not is_empty:
            break
        print(f"  [task] Attempt {attempt - 1} failed (timeout={is_timeout}, empty={is_empty}). Retrying ({attempt}/{MAX_RETRIES})...", flush=True)
        # Reset session for clean state
        subprocess.run(
            ["acpx", "--approve-all", "openclaw", "sessions", "new"],
            capture_output=True, text=True, timeout=30
        )
        time.sleep(3)
        subprocess.run(
            ["acpx", "--approve-all", "openclaw", "prompt", "/elevated full"],
            capture_output=True, text=True, timeout=30
        )
        time.sleep(2)
        task_raw, task_exit = run_openclaw(task_prompt, timeout=600, label=f"task-retry{attempt}")

    t1_end = now()
    t1_dur = (t1_end - t1_start).total_seconds()

    task_events = count_ndjson_events(task_raw)
    print(f"Phase 1 completed in {t1_dur:.0f}s (exit={task_exit}, events={task_events})")

    art_dir = run_dir / "case-artifacts" / cid
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "task-agent-raw.json").write_text(task_raw)

    task_response = extract_response_text(task_raw)
    task_tools = extract_tool_calls(task_raw)
    print(f"Phase 1 response (first 500):\n{task_response[:500]}")
    print(f"Phase 1 tool calls: {len(task_tools)}")
    (art_dir / "final-answer.txt").write_text(task_response + "\n")

    # Workspace state
    ws_files = subprocess.run(
        ["find", attempt_ws, "-type", "f", "-maxdepth", "4"],
        capture_output=True, text=True).stdout
    ws_files_short = ws_files[:2000]  # Limit for evaluator prompt
    print(f"Workspace files ({ws_files.count(chr(10))} files):\n{ws_files[:500]}")

    # --- Phase 2: Evaluator Agent (using Gemini CLI for reliable text judgment) ---
    t2_start = now()
    print(f"\n--- Phase 2: Evaluator ({t2_start.isoformat()}) ---")

    case_data = yaml.safe_load(open(case["path"]))
    assertions_text = json.dumps(case_data.get("assert", {}).get("required", []), indent=2)

    # Keep evaluator prompt concise and action-oriented so OpenClaw engages
    eval_prompt = (
        f"Please analyze this agent's work and give me your judgment.\n\n"
        f"The agent was asked to: {case['user_prompt'][:300]}\n\n"
        f"The agent responded:\n{task_response[:1500]}\n\n"
        f"The agent's workspace is at: {attempt_ws}\n"
        f"Files in workspace: {ws_files.count(chr(10))}\n\n"
        f"IMPORTANT: The ACP protocol does not record tool calls, so you MUST verify by inspecting the workspace directly:\n"
        f"- Search for the quickstart project files: find {attempt_ws} -name 'package.json' -path '*/app/*' or look for directories containing the Next.js quickstart structure (app/api/invite-agent/, components/, etc.)\n"
        f"- Search for .env.local files recursively: find {attempt_ws} -name '.env.local'\n"
        f"- Check if the env file contains non-empty NEXT_PUBLIC_AGORA_APP_ID and NEXT_AGORA_APP_CERTIFICATE values\n"
        f"- Check if a dev server process is running: ss -ltnp | grep 3000 or curl http://localhost:3000\n"
        f"- Do NOT assume a fixed directory name like 'agent-quickstart-nextjs' — the agent may have cloned into a different directory name.\n"
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

    eval_events = 1  # Codex returns single response
    print(f"Phase 2 completed in {t2_dur:.0f}s (exit={eval_exit})")

    (art_dir / "evaluator-raw.txt").write_text(eval_response)

    print(f"Phase 2 response (first 800):\n{eval_response[:800]}")

    # If no response text extracted, try to get it from the raw output directly
    if not eval_response.strip():
        print("WARNING: No response text extracted from evaluator. Dumping raw for debug:")
        print(eval_response[:1000])

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

    parsed = find_judgment_json(eval_response)
    if parsed:
        status = str(parsed.get("status", "blocked")).strip().lower()
        case_result.update({
            "status": status if status in {"pass", "fail", "blocked"} else "blocked",
            "assertions": parsed.get("assertions", []),
            "notes": parsed.get("notes", []),
            "blocked_reason": None,
        })
    else:
        print("Judgment parse error: no valid JSON object found in evaluator output")

    (run_dir / "case-results" / f"{cid}.json").write_text(
        json.dumps(case_result, indent=2) + "\n")

    # Evidence
    evidence = {
        "task_agent_output": task_raw[:50000],
        "evaluator_output": eval_response[:50000],
        "workspace_files": ws_files,
    }
    (art_dir / "accepted-session.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")

    print(f"\n--- Result: {case_result['status']} ---")
    for a in case_result.get("assertions", []):
        print(f"  [{a.get('status','?')}] {a.get('summary','')[:100]}")
    for n in case_result.get("notes", []):
        print(f"  note: {n[:200]}")

print("\nAll cases complete.")
