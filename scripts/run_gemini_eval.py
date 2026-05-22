#!/usr/bin/env python3
"""Two-phase Gemini CLI evaluation: task agent + evaluator agent."""
import json, subprocess, os, datetime, yaml, re, sys
from pathlib import Path
from json import JSONDecoder

run_dir = Path(os.environ["RUN_DIR"])
cases = json.loads(Path("/tmp/gemini-eval-cases.json").read_text())
model_flag = os.environ.get("GEMINI_MODEL", "")
repo_root = Path.cwd()

def now():
    return datetime.datetime.now(datetime.timezone.utc)

def run_gemini(prompt, timeout=600):
    cmd = ["gemini", "--yolo", "--prompt", prompt, "--output-format", "json"]
    if model_flag:
        cmd.extend(["--model", model_flag])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


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
    ws = Path(f"/tmp/gemini-eval-{cid}")
    ws.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["bash", ".agents/skills/skills-evaluation/scripts/create_case_workspace.sh",
         str(repo_root), str(ws), cid, "--target", os.environ.get("TARGET_ID", "agora")],
        capture_output=True, text=True)
    attempt_ws = result.stdout.strip() or str(ws)
    print(f"Workspace: {attempt_ws}")

    # --- Phase 1: Task Agent ---
    t1_start = now()
    print(f"\n--- Phase 1: Task Agent (started {t1_start.isoformat()}) ---")

    task_prompt = (
        f"You are working in workspace: {attempt_ws}\n\n"
        f"Task: answer this user request naturally, using the workspace as needed:\n"
        f'"{case["user_prompt"]}"\n\n'
        f"Requirements:\n"
        f"- Treat {attempt_ws} as your only workspace.\n"
        f"- Keep all file reads, writes, and shell commands inside it.\n"
        f"- Use the skill docs in .agents/skills/ if relevant.\n"
        f"- Give the exact answer you would send to the user."
    )

    task_result = run_gemini(task_prompt)
    t1_end = now()
    t1_dur = (t1_end - t1_start).total_seconds()
    print(f"Phase 1 completed in {t1_dur:.0f}s (exit={task_result.returncode})")

    if task_result.stderr:
        print(f"Phase 1 stderr (first 300): {task_result.stderr[:300]}")

    # Parse task output
    art_dir = run_dir / "case-artifacts" / cid
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "task-agent-raw.json").write_text(task_result.stdout)

    task_response = ""
    task_tools = {}
    try:
        task_data = json.loads(task_result.stdout)
        task_response = task_data.get("response", "")
        task_tools = task_data.get("stats", {}).get("tools", {}).get("byName", {})
    except Exception as e:
        print(f"Phase 1 JSON parse error: {e}")
        task_response = task_result.stdout[:5000]

    print(f"\nPhase 1 response (first 500):\n{task_response[:500]}")
    print(f"\nPhase 1 tools: {json.dumps(task_tools)}")
    (art_dir / "final-answer.txt").write_text(task_response + "\n")

    # Workspace state
    ws_files = subprocess.run(
        ["find", attempt_ws, "-type", "f", "-maxdepth", "4"],
        capture_output=True, text=True).stdout
    print(f"\nWorkspace files:\n{ws_files[:500]}")

    # --- Phase 2: Evaluator Agent ---
    t2_start = now()
    print(f"\n--- Phase 2: Evaluator (started {t2_start.isoformat()}) ---")

    case_data = yaml.safe_load(open(case["path"]))
    assertions_text = json.dumps(case_data.get("assert", {}).get("required", []), indent=2)

    eval_prompt = (
        "You are an independent evaluator judging a DIFFERENT agent's work.\n"
        "Do NOT execute commands. Only read evidence and judge.\n\n"
        f"Task prompt given to the agent:\n---\n{case['user_prompt']}\n---\n\n"
        f"Agent response:\n---\n{task_response}\n---\n\n"
        f"Tools the agent used: {json.dumps(task_tools)}\n\n"
        f"Files in workspace after agent ran:\n{ws_files}\n\n"
        f"Assertions to judge:\n{assertions_text}\n\n"
        "For each assertion: PASS or FAIL with specific evidence.\n"
        "Output ONLY valid JSON (no markdown wrapping):\n"
        '{"case_id": "' + cid + '", "status": "pass or fail", '
        '"assertions": [{"summary": "...", "status": "pass or fail", "evidence": ["..."]}], '
        '"notes": ["..."]}'
    )

    eval_result = run_gemini(eval_prompt, timeout=300)
    t2_end = now()
    t2_dur = (t2_end - t2_start).total_seconds()
    print(f"Phase 2 completed in {t2_dur:.0f}s (exit={eval_result.returncode})")

    if eval_result.stderr:
        print(f"Phase 2 stderr (first 300): {eval_result.stderr[:300]}")

    (art_dir / "evaluator-raw.json").write_text(eval_result.stdout)

    # Parse evaluator response
    eval_response = ""
    try:
        eval_data = json.loads(eval_result.stdout)
        eval_response = eval_data.get("response", "")
    except Exception as e:
        print(f"Phase 2 JSON parse error: {e}")
        eval_response = eval_result.stdout[:5000]

    print(f"\nPhase 2 response (first 800):\n{eval_response[:800]}")

    # Extract judgment JSON
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

    parsed = find_judgment_json(eval_response or eval_result.stdout)
    if parsed:
        status = str(parsed.get("status", "blocked")).strip().lower()
        case_result.update({
            "status": status if status in {"pass", "fail", "blocked"} else "blocked",
            "assertions": parsed.get("assertions", []),
            "notes": parsed.get("notes", []),
            "blocked_reason": None,
        })
    else:
        print("Judgment JSON parse error: no valid JSON object found in evaluator output")

    (run_dir / "case-results" / f"{cid}.json").write_text(
        json.dumps(case_result, indent=2) + "\n")

    # Evidence bundle
    evidence = {
        "task_agent_output": task_result.stdout[:50000],
        "evaluator_output": eval_result.stdout[:50000],
        "workspace_files": ws_files,
    }
    (art_dir / "accepted-session.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")

    # Summary
    print(f"\n--- Result: {case_result['status']} ---")
    for a in case_result.get("assertions", []):
        print(f"  [{a.get('status','?')}] {a.get('summary','')[:100]}")
    for n in case_result.get("notes", []):
        print(f"  note: {n[:200]}")

print("\nAll cases complete.")
