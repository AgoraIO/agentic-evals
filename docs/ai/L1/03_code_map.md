# 03 Code Map

> Navigate the repository quickly and locate contracts, test definitions, and execution helpers.

## Top-Level Map

```text
agentic-evals/
├── AGENT.md
├── AGENTS.md
├── README.md
├── VERSION
├── docs/
├── evaluations/
├── rubrics/
├── scripts/
└── targets/
```

## Directory Responsibilities

| Path | Responsibility |
| --- | --- |
| `AGENT.md` | Evaluator contract and required workflow |
| `docs/session-evidence.md` | Session evidence extraction and isolation rules |
| `targets/` | Target-specific suites and case assertions |
| `evaluations/` | Higher-level AB/comparison/subjective configs |
| `rubrics/default.yaml` | Scoring dimensions for subjective/comparison modes |
| `scripts/` | Runtime runners and reporting helpers |

## Targets Tree

- `targets/agora/target.yaml`
- `targets/voice-ai-integration/target.yaml`
- `targets/<id>/cases/<suite_id>/suite.yaml`
- `targets/<id>/cases/<suite_id>/<case_id>.yaml`

## Script Entry Points

| Script | Role |
| --- | --- |
| `scripts/run_openclaw_eval.py` | Two-phase OpenClaw task + evaluator execution |
| `scripts/run_gemini_eval.py` | Two-phase Gemini flow |
| `scripts/run_hermes_eval.py` | Hermes execution flow |
| `scripts/run_hermes_subagent_eval.py` | Hermes evaluator invoking sub-agent |
| `scripts/analyze_codex_session.py` | Parse Codex session JSONL for isolation and evidence |
| `scripts/generate_report.py` | Build `report.md` from `case-results/*.json` |
| `scripts/notify_feishu.py` | Optional Feishu notification sink |

## Artifact Paths

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/transcript.md`
- `runs/<run_id>/case-artifacts/<case_id>/accepted-session.json`
- `runs/<run_id>/case-results/<case_id>.json`
- `runs/<run_id>/report.md`

## Frequent Navigation Paths

- Contract-first changes: `AGENT.md` -> `targets/<id>/target.yaml` -> affected case files
- Evidence logic changes: `docs/session-evidence.md` -> runtime script parser blocks
- Reporting changes: `scripts/generate_report.py` -> sample `case-results/*.json`
- Evaluation orchestration changes: `evaluations/README.md` -> `evaluations/*/*.yaml`

## Where To Edit For Common Changes

- Add or refine behavior checks: case YAML under target suite directory
- Change default suite selection: target `default_suites`
- Change allowed statuses: target `allowed_statuses`
- Change evaluator output summary: `scripts/generate_report.py`
- Change evidence interpretation: `docs/session-evidence.md` and evaluator logic

## File Discovery Shortcuts

```bash
rg --files targets
rg --files scripts
rg -n "allowed_statuses|default_suites|artifact_contract" targets
```

## Related Deep Dives

- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Path lifecycle and workspace materialization.
- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Script-level runtime behavior and outputs.
