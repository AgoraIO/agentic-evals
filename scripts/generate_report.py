#!/usr/bin/env python3
"""Generate report.md from case-results JSON files."""
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
results_dir = run_dir / "case-results"

if not results_dir.exists():
    print("No case-results directory found")
    (run_dir / "report.md").write_text("# Report\n\nNo results found.\n")
    exit(0)

cases = []
for f in sorted(results_dir.glob("*.json")):
    cases.append(json.loads(f.read_text()))

total = len(cases)
passed = sum(1 for c in cases if c["status"] == "pass")
failed = sum(1 for c in cases if c["status"] == "fail")
blocked = sum(1 for c in cases if c["status"] == "blocked")

def fmt(s):
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"

manifest_path = run_dir / "manifest.json"
runtime = "unknown"
if manifest_path.exists():
    m = json.loads(manifest_path.read_text())
    runtime = m.get("runtime", "unknown")

lines = [
    f"# Skill Eval Report ({runtime})", "",
    f"- runtime: {runtime} (two-phase)",
    f"- cases: {total} ({passed} pass, {failed} fail, {blocked} blocked)", "",
    "## Case Table", "",
    "| case_id | status |",
    "|---|---|",
]
for c in cases:
    lines.append(f"| {c['case_id']} | {c['status']} |")

lines += ["", "## Timing", "",
    "| case_id | task_execution | verification | total |",
    "|---|---|---|---|"]
for c in cases:
    lines.append(f"| {c['case_id']} | {fmt(c.get('task_duration_s',0))} | {fmt(c.get('verification_duration_s',0))} | {fmt(c.get('total_duration_s',0))} |")

lines += ["", "## Assertion Details", ""]
for c in cases:
    lines.append(f"### {c['case_id']} — {c['status']}")
    for a in c.get("assertions", []):
        lines.append(f"- [{a.get('status','?')}] {a.get('summary','')}")
        for e in a.get("evidence", [])[:2]:
            lines.append(f"  - {e}")
    notes = c.get("notes", [])
    if isinstance(notes, str):
        notes = [notes]
    for n in notes:
        lines.append(f"- note: {n}")
    lines.append("")

lines += ["## Suggested Next Fixes", ""]
if failed == 0 and blocked == 0:
    lines.append("None — all cases passed.")
else:
    for c in cases:
        if c["status"] != "pass":
            lines.append(f"- {c['case_id']}: see case-results/{c['case_id']}.json")
lines.append("")

(run_dir / "report.md").write_text("\n".join(lines))

# Update manifest
mf = run_dir / "manifest.json"
if mf.exists():
    m = json.loads(mf.read_text())
    m["result_counts"] = {"pass": passed, "fail": failed, "blocked": blocked}
    mf.write_text(json.dumps(m, indent=2))

print(f"Report: {passed} pass, {failed} fail, {blocked} blocked")
