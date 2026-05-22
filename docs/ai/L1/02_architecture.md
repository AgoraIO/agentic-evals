# 02 Architecture

> High-level system design for targets, cases, evaluator scripts, and run artifacts.

## System Overview

`agentic-evals` is a contract-first evaluation repository.

- `targets/` defines behavior expectations
- `scripts/` orchestrate runtime execution and judgment
- `runs/` holds materialized evidence and reports
- `AGENT.md` defines the canonical execution order and artifact contract

## Core Flow

```text
target.yaml + suite.yaml + case.yaml
            |
            v
  evaluator runtime (codex/openclaw/gemini/hermes)
            |
            v
  isolated case workspace per case
            |
            v
  accepted session evidence + final answer
            |
            v
  case-results/<case_id>.json + report.md
```

## Run Modes

- `single-run`: one target skill workspace, one result set
- `ab-urls`: two isolated variants (A/B), same resolved case set, plus comparison outputs

## Authoritative Contracts

- [AGENT.md](../../../AGENT.md) controls required artifact shape
- [docs/session-evidence.md](../../../docs/session-evidence.md) controls evidence extraction and isolation interpretation
- `target.yaml` controls `allowed_statuses` and default suites

## Evaluator Responsibilities

- Resolve target and case set before execution
- Execute each case in a fresh workspace
- Locate accepted child session evidence
- Generate per-case judgment and aggregate report
- Mark `blocked` if evidence is insufficient

## Case Artifact Shape

```text
runs/<run_id>/
├── manifest.json
├── case-artifacts/<case_id>/
│   ├── accepted-session.json
│   └── final-answer.txt
├── transcript.md
├── case-results/<case_id>.json
└── report.md
```

## AB Wrapper Shape

`ab-urls` adds top-level comparison wrappers with `variants/A` and `variants/B`.

- each variant still contains a regular `single-run` structure
- top-level run writes `comparison.json` and a comparison `report.md`

## Coupling Boundaries

- Case meaning lives in YAML case files, not runtime scripts
- Runtime scripts may vary but must write compatible artifacts
- Rubric scoring is additive to pass/fail assertions

## Evolution Model

- Add new cases without changing runtime logic where possible
- Update `AGENT.md` only for contract-level changes
- Keep runtime-specific quirks in L2 docs to avoid polluting case semantics

## Related Deep Dives

- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime-specific orchestration details.
- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Attempt workspace creation, isolation, and evidence retention.
