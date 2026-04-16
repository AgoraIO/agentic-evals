#!/usr/bin/env python3
"""
Hermes evaluator with sub-agent execution (mirrors Codex spawn_agent pattern).

Architecture:
  - Python script sets up workspace and builds the evaluator prompt
  - A single hermes invocation acts as the EVALUATOR (main agent)
  - The evaluator prompt instructs hermes to:
    1. Spawn a sub-agent via shell: `hermes chat --yolo --quiet -q "<task_prompt>"`
    2. Wait for the sub-agent to finish (it's a blocking shell call)
    3. Inspect the workspace and running processes independently
    4. Judge assertions and output structured JSON

  Context isolation:
  - The sub-agent (hermes child process) only receives the user prompt + workspace path
  - The sub-agent does NOT see assertions, expected outcomes, or evaluator instructions
  - The evaluator sees the sub-agent's stdout but judges from workspace inspection
"""
import json, subprocess, os, datetime, re, sys
from pathlib import Path

sys.stdout.reconfigure(line_buffering=True)
print("=== Hermes evaluator+subagent eval starting ===", flush=True)

try:
    import yaml
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

run_dir = Path(os.environ["RUN_DIR"])
cases_file = Path("/tmp/hermes-eval-cases.json")
if not cases_file.exists():
    print(f"ERROR: {cases_file} not found!", flush=True)
    sys.exit(1)

cases = json.loads(cases_file.read_text())
repo_root = Path.cwd()
model_flag = os.environ.get("HERMES_MODEL", "")
print(f"RUN_DIR={run_dir} Cases={len(cases)}", flush=True)


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def run_hermes(prompt, timeout=900, label="evaluator", cwd=None):
    """Run hermes chat one-shot."""
    cmd = ["hermes", "chat", "--yolo", "--quiet", "-q", prompt]
    if model_flag:
        cmd.extend(["--model", model_flag])
    print(f"  [{label}] hermes chat -q (cwd={cwd}, timeout={timeout}s)")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env={**os.environ}, cwd=cwd)
        return r.stdout, r.returncode, r.stderr
    except subprocess.TimeoutExpired:
        print(f"  [{label}] TIMEOUT {timeout}s")
        return "", -1, f"TIMEOUT after {timeout}s"


def setup_workspace(cid):
    ws = Path(f"/tmp/hermes-eval-{cid}")
    ws.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["bash", ".agents/skills/skills-evaluation/scripts/create_case_workspace.sh",
         str(repo_root), str(ws), cid, "--target", os.environ.get("TARGET_ID", "agora")],
        capture_output=True, text=True)
    attempt_ws = r.stdout.strip().split("\n")[-1] if r.stdout.strip() else str(ws)
    if r.returncode != 0:
        print(f"Workspace script failed (exit={r.returncode})")
        attempt_ws = str(ws / cid / "attempt-01")
        os.makedirs(attempt_ws, exist_ok=True)
        src = str(repo_root / ".agents")
        dst = os.path.join(attempt_ws, ".agents")
        subprocess.run(["cp", "-rL", src, dst], capture_output=True)
    return attempt_ws


def build_subagent_task_prompt(case, attempt_ws):
    """The prompt that the sub-agent receives. No assertions, no eval context."""
    return (
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
        f"- The environment variables AGORA_APP_ID and AGORA_APP_CERTIFICATE are set and available.\n"
        f"  Use their literal values (echo $AGORA_APP_ID) when writing config files — do NOT write "
        f"shell variable syntax like ${{AGORA_APP_ID}} into files.\n"
        f"- If git clone over HTTPS fails, use tarball download instead: "
        f"curl -L https://github.com/OWNER/REPO/archive/refs/heads/main.tar.gz | tar xz\n"
        f"- When starting a dev server (e.g. npm run dev, pnpm dev), you MUST launch it as a background process "
        f"(e.g. `nohup pnpm dev > /dev/null 2>&1 &` or use the process tool) so it keeps running after you finish.\n"
        f"- After starting the server, verify it is listening (e.g. curl -I http://localhost:3000) before reporting success.\n"
        f"- IMPORTANT: After the server responds to HEAD requests, also do a full GET request to warm up the page:\n"
        f"  curl -s -o /dev/null -w '%{{http_code}}' --max-time 120 http://localhost:3000\n"
        f"  This triggers Next.js page compilation. Wait for it to complete before reporting success.\n"
        f"  If the first GET times out, wait 15 seconds and retry once.\n"
        f"- Give the exact answer you would send to the user."
    )


def build_evaluator_prompt(case, attempt_ws, assertions_text, cid, subagent_cmd):
    """
    The evaluator (main agent) prompt. It will:
    1. Spawn the sub-agent via shell command
    2. Wait for it to complete
    3. Independently verify the workspace
    4. Output judgment JSON
    """
    return (
        f"You are the skill-eval evaluator agent.\n\n"
        f"## Step 1: Execute the task via sub-agent\n\n"
        f"Run this shell command to spawn an isolated sub-agent that will execute the task:\n\n"
        f"```\n{subagent_cmd}\n```\n\n"
        f"This command runs a SEPARATE hermes agent process. It will:\n"
        f"- Read skill docs in the workspace\n"
        f"- Clone repos, configure files, start servers as needed\n"
        f"- Print its response to stdout\n\n"
        f"Wait for it to complete. Save its stdout output — this is the sub-agent's response.\n"
        f"The sub-agent does NOT know about the assertions below. It only received the user's request.\n\n"
        f"## Step 2: Verify independently\n\n"
        f"After the sub-agent finishes, YOU must verify the workspace at: {attempt_ws}\n\n"
        f"Do NOT trust the sub-agent's self-report. Inspect everything yourself:\n"
        f"- Check if {attempt_ws}/agent-quickstart-nextjs exists (git clone evidence)\n"
        f"- Check if a .env.local file exists with real Agora credentials (not placeholders)\n"
        f"- Check if a dev server process is running (use: lsof -i :3000 or curl -I http://localhost:3000)\n"
        f"- For browser/page-load verification, follow this EXACT sequence:\n"
        f"  a) WARM UP FIRST: Next.js dev servers compile pages on first GET, which can take 30-120s.\n"
        f"     Run: curl -s -o /dev/null -w '%{{http_code}}' --max-time 120 http://localhost:3000\n"
        f"     If it times out, wait 30 seconds and retry the same curl command.\n"
        f"     Do NOT proceed to browser verification until curl GET returns 200.\n"
        f"  b) After warm-up succeeds, use your built-in browser_navigate tool to open http://localhost:3000.\n"
        f"     Do NOT use agent-browser. Use hermes's own browser tool.\n"
        f"     If localhost fails, retry with http://127.0.0.1:3000.\n"
        f"  c) If browser tool also fails after warm-up, fall back to:\n"
        f"     curl -s --max-time 30 http://localhost:3000 | head -100\n"
        f"     and check the HTML body contains expected page content (title, Next.js markup).\n"
        f"  d) curl 200 + valid HTML body is acceptable as a pass for the browser assertion.\n\n"
        f"Check these assertions:\n{assertions_text}\n\n"
        f"## Step 3: Output judgment\n\n"
        f"Write your answer as a JSON object:\n"
        f'{{"case_id": "{cid}", "status": "pass or fail", '
        f'"assertions": [{{"summary": "description", "status": "pass or fail", "evidence": ["what you observed"]}}], '
        f'"notes": ["any observations"]}}\n\n'
        f'"status" = "pass" only if ALL assertions pass.\n'
        f"Run the sub-agent command and verification now."
    )


def parse_judgment(text):
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("{") and "case_id" in line:
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


# === Main loop ===
for case in cases:
    cid = case["case_id"]
    print(f"\n{'='*60}\nCase: {cid}\n{'='*60}")

    attempt_ws = setup_workspace(cid)
    print(f"Workspace: {attempt_ws}")

    case_data = yaml.safe_load(open(case["path"]))
    assertions_text = json.dumps(
        case_data.get("assert", {}).get("required", []), indent=2)

    # Build the sub-agent command that the evaluator will execute via shell
    task_prompt = build_subagent_task_prompt(case, attempt_ws)
    # Escape single quotes in the prompt for shell safety
    escaped_prompt = task_prompt.replace("'", "'\\''")
    subagent_cmd = f"hermes chat --yolo --quiet -q '{escaped_prompt}'"
    if model_flag:
        subagent_cmd += f" --model '{model_flag}'"

    t_start = now()
    print(f"\n--- Evaluator+SubAgent ({t_start.isoformat()}) ---", flush=True)

    eval_prompt = build_evaluator_prompt(
        case, attempt_ws, assertions_text, cid, subagent_cmd)
    stdout, exitcode, stderr = run_hermes(
        eval_prompt, timeout=900, label="evaluator", cwd=attempt_ws)

    t_end = now()
    t_dur = (t_end - t_start).total_seconds()
    print(f"Done in {t_dur:.0f}s (exit={exitcode})")

    # Save artifacts
    art_dir = run_dir / "case-artifacts" / cid
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "evaluator-raw.txt").write_text(stdout)
    if stderr:
        (art_dir / "evaluator-stderr.txt").write_text(stderr)
    (art_dir / "final-answer.txt").write_text(stdout + "\n")

    print(f"Response (first 500):\n{stdout[:500]}")

    # Workspace state
    ws_files = subprocess.run(
        ["find", attempt_ws, "-type", "f", "-maxdepth", "4"],
        capture_output=True, text=True).stdout

    # Parse judgment
    case_result = {
        "case_id": cid, "status": "blocked",
        "blocked_reason": "evaluator-parse-error", "assertions": [],
        "notes": ["Could not parse evaluator response"],
        "started_at": t_start.isoformat(),
        "completed_at": t_end.isoformat(),
        "total_duration_s": round(t_dur),
        "workspace_root": attempt_ws,
        "mode": "hermes-evaluator-subagent",
    }

    parsed = parse_judgment(stdout)
    if parsed:
        case_result.update({
            "status": parsed.get("status", "blocked"),
            "assertions": parsed.get("assertions", []),
            "notes": parsed.get("notes", []),
            "blocked_reason": None,
        })

    (run_dir / "case-results" / f"{cid}.json").write_text(
        json.dumps(case_result, indent=2) + "\n")

    # Evidence bundle
    evidence = {
        "evaluator_output": stdout[:50000],
        "evaluator_stderr": (stderr or "")[:10000],
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
