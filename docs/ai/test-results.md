# PD Documentation Test Results

Tested: 2026-05-22
Agent: Codex (GPT-5)
Repo: agentic-evals

## Summary

- Total questions: 10
- Passed: 10 (correct answer, right level)
- L1 gaps: 0
- L2 gaps: 0
- Cross-ref issues: 0

## Structural Checks

- L0 exists and is under 50 lines: pass (`docs/ai/L0_repo_card.md` is 29 lines)
- All 8 L1 files exist: pass
- Each L1 file is 80-200 lines: pass
- L1 combined line count under 1,600: pass (683)
- L1 files include purpose statement and `## Related Deep Dives`: pass
- `docs/ai/L1/L2/_index.md` exists and lists all L2 docs: pass
- Each L2 file starts with `> **When to Read This:**`: pass
- Relative links resolve: pass
- `AGENTS.md` exists and includes How to Load, Git Conventions, Doc Commands: pass
- `CLAUDE.md` reference check: not applicable (`CLAUDE.md` does not exist)

## Results

### Setup & Build

| # | Question | Answer Correct? | Files Read | Level Loaded | Result |
| - | -------- | --------------- | ---------- | ------------ | ------ |
| 1 | How do I validate YAML integrity for a target? | Yes | L0, 01_setup, README | L0+L1 | Pass |
| 2 | What environment variables are required by runtime scripts? | Yes | L0, 01_setup, scripts/*.py | L0+L1 | Pass |

### Test & Run

| # | Question | Answer Correct? | Files Read | Level Loaded | Result |
| - | -------- | --------------- | ---------- | ------------ | ------ |
| 3 | How do I generate `report.md` from case results? | Yes | L0, 05_workflows, scripts/generate_report.py | L0+L1 | Pass |
| 4 | What artifact files are required in a single-run output? | Yes | L0, 02_architecture, AGENT.md | L0+L1 | Pass |

### Conventions

| # | Question | Answer Correct? | Files Read | Level Loaded | Result |
| - | -------- | --------------- | ---------- | ------------ | ------ |
| 5 | What naming and suite-reference conventions apply to case authoring? | Yes | L0, 04_conventions, README | L0+L1 | Pass |
| 6 | How should uncertain evidence be handled in judgments? | Yes | L0, 07_gotchas, docs/session-evidence.md | L0+L1 | Pass |

### Development

| # | Question | Answer Correct? | Files Read | Level Loaded | Result |
| - | -------- | --------------- | ---------- | ------------ | ------ |
| 7 | How do I add a new runnable case without breaking activation? | Yes | L0, 05_workflows, targets/*/cases/*/suite.yaml | L0+L1 | Pass |
| 8 | Where do I change allowed statuses and default suites for a target? | Yes | L0, 03_code_map, 06_interfaces, targets/*/target.yaml | L0+L1 | Pass |

### Deep Dive

| # | Question | Answer Correct? | Files Read | Level Loaded | Result |
| - | -------- | --------------- | ---------- | ------------ | ------ |
| 9 | How is isolation judged when `session_meta.cwd` is misleading? | Yes | L0, 08_security, L2/case_workspace_lifecycle, docs/session-evidence.md | L2 required and used | Pass |
| 10 | How do runtime scripts normalize parser failures across models? | Yes | L0, 06_interfaces, L2/evaluator_runtimes, scripts/run_gemini_eval.py | L2 required and used | Pass |

## Recommended Fixes

- [x] Fix relative links from L1 docs to repo-root files (`AGENT.md`, `docs/session-evidence.md`)
- [x] Expand short L1 files to meet line budget and improve scanability
- [x] Add L2 docs for runtime behavior and workspace lifecycle

## Review Fix Retest

Retested: 2026-05-22

| Finding | Source checked | Docs changed | Result | Notes |
| ------- | -------------- | ------------ | ------ | ----- |
| Broken relative links to root docs from L1 | `AGENT.md`, `docs/session-evidence.md` | `docs/ai/L1/01_setup.md`, `docs/ai/L1/02_architecture.md` | Pass | Link resolver reports zero missing links |
| L1 files below line target | L1 file line counts and structure checklist | `docs/ai/L1/03_code_map.md`, `docs/ai/L1/04_conventions.md`, `docs/ai/L1/05_workflows.md`, `docs/ai/L1/07_gotchas.md`, `docs/ai/L1/08_security.md` | Pass | All L1 files now 80-200 lines |
