# Agent Contract For `agentic-evals`

This file is the agent-facing contract for evaluator agents such as `skill-eval`.

## Purpose

`agentic-evals` is a target-driven evaluation repo for testing one skill at a time.

This repo is the source of truth for:

- targets
- suites
- cases
- assertions
- evaluations (AB tests, subjective scoring, vendor comparisons)
- rubrics (scoring dimensions)
- required run artifacts
- report shape

The target skill remains the source of truth for the behavior being tested.
The evaluator must not invent new rules when this repo is silent.

If a case cannot be judged reliably from the available evidence, mark it `blocked`.

The current default target is `voice-ai-integration`.

## Run Modes

This repo supports 2 evaluator run modes:

- `single-run`: the existing one-skill evaluation flow
- `ab-urls`: a top-level comparison flow that prepares 2 isolated skill variants from URLs and runs the same case set twice

`single-run` remains the baseline contract.
`ab-urls` adds a top-level orchestrator artifact shape around 2 variant-local `single-run` executions.
It does not change case semantics, assertion semantics, or allowed case statuses.

## Run Workflow

Every evaluator that uses this repo should follow this order:

1. Read this file.
2. Resolve `run_mode`. If omitted, use `single-run`.
3. Resolve `target_id`. If none is provided, use the repo default target.
4. Read `targets/<target_id>/target.yaml`.
5. Read the selected suite files from `targets/<target_id>/cases/<suite_id>/suite.yaml`.
6. Read each case file referenced by those suites, or the selected case file.
7. Create `runs/<run_id>/manifest.json`.
8. If `run_mode` is `ab-urls`, prepare 2 variant source workspaces before any case execution.
9. Create a parent temp directory for isolated per-case workspaces.
10. Execute each case in its own fresh isolated workspace.
11. Locate the accepted fresh-agent evidence for each case.
12. Save the accepted evidence for each case.
13. Render a readable `transcript.md` from the accepted evidence.
14. Write one `case-results/<case_id>.json` file per case.
15. Write `report.md`.
16. If `run_mode` is `ab-urls`, join the 2 variant result sets by `case_id`, then write `comparison.json` and the top-level comparison `report.md`.

Do not start execution before the case set is known.
In `ab-urls`, both variants must use the exact same resolved case set.

## Repo Layout

```text
agentic-evals/
├── AGENT.md
├── README.md
├── docs/
│   └── session-evidence.md
├── targets/
│   └── <target_id>/
│       ├── target.yaml
│       └── cases/
│           └── <suite_id>/
│               ├── suite.yaml
│               └── <case_id>.yaml
├── evaluations/
│   ├── ab/
│   ├── comparison/
│   └── subjective/
├── rubrics/
│   └── default.yaml
└── runs/
```

## Source Of Truth

- `targets/<target_id>/target.yaml` defines the target under test, the entry skill, the skill roots that may be consulted, the default suites, the required run artifacts, and the allowed statuses.
- `targets/<target_id>/cases/<suite_id>/suite.yaml` defines a runnable suite and lists its cases.
- `targets/<target_id>/cases/<suite_id>/<case_id>.yaml` holds active cases, co-located with their suite.
- `targets/<target_id>/deferred-cases/` holds backlog cases that are intentionally not active.
- `docs/session-evidence.md` defines the dual-mode session evidence model for Codex and OpenClaw runtimes.

Deferred cases are not part of the runnable active suite set unless a human explicitly promotes them.

## Required Run Artifacts

### `single-run`

Each `single-run` must create:

```text
runs/<run_id>/
├── manifest.json
├── case-artifacts/
│   ├── <case_id>/
│   │   ├── accepted-session.json
│   │   └── final-answer.txt
│   └── ...
├── transcript.md
├── case-results/
│   ├── <case_id>.json
│   └── ...
└── report.md
```

`manifest.json` must record:

- `run_mode` with value `single-run`
- `run_id`
- `target_id`
- `suite_ids`
- `target_skill_path`
- `started_at`
- `model` if available
- `workspace_mode` with value `isolated-per-case`
- `case_workspace_root` for the parent temp directory used for per-case workspaces
- `evidence_mode` with one of:
  - `codex-local-session-store`
  - `codex-direct-process`
  - `openclaw-session-history`
- `notes` if the environment is unusual

It is also acceptable to record extra fields such as `selected_case_ids`, `resolved_case_ids`, `source_workspace`, `run_state`, `variant_label`, or `variant_source_url`.

Each case result must record that case's accepted `workspace_root`.

### `ab-urls`

Each `ab-urls` top-level run must create:

```text
runs/<ab_run_id>/
├── manifest.json
├── variants/
│   ├── A/
│   │   ├── source-manifest.json
│   │   └── run/
│   │       ├── manifest.json
│   │       ├── case-artifacts/
│   │       ├── transcript.md
│   │       ├── case-results/
│   │       └── report.md
│   └── B/
│       ├── source-manifest.json
│       └── run/
│           ├── manifest.json
│           ├── case-artifacts/
│           ├── transcript.md
│           ├── case-results/
│           └── report.md
├── comparison.json
└── report.md
```

Rules:

- `variants/<label>/run/` must follow the same artifact shape as `single-run`.
- the A and B source workspaces must be isolated from each other and must not share the target skill directory
- the 2 variant runs must resolve the same `target.yaml`, suite set, and case set
- the top-level `ab-urls` run is responsible only for variant acquisition, variant run coordination, and comparison
- `agentic-evals` remains the only source of truth for case meaning and assertion meaning

`runs/<ab_run_id>/manifest.json` must record:

- `run_mode` with value `ab-urls`
- `run_id`
- `target_id`
- `suite_ids`
- `selected_case_ids` when applicable
- `resolved_case_ids`
- `started_at`
- `evidence_mode`
- `variants` with A/B source URLs and relative artifact paths
- `notes` when the environment is unusual

Each `variants/<label>/source-manifest.json` should record at least:

- `label`
- `source_url`
- normalized URL parse output such as `repo_url`, `ref`, `subdir`, `ref_type`, and `checkout_ref`
- `checkout_dir`
- `resolved_skill_dir`
- `prepared_source_workspace`
- `status`
- `error` when acquisition failed

If a variant URL cannot be parsed, downloaded, checked out, or resolved to a skill root:

- mark that variant as an acquisition failure
- do not judge cases for that variant
- continue the other variant if possible
- mark the top-level A/B run `blocked` or `partial`
- state clearly which side failed and why

If acquisition fails before a variant can run cases, the evaluator may still initialize `variants/<label>/run/` as a blocked skeleton with `run_state: acquisition-failed`.

## Case Status

- `pass`: all required assertions passed with enough evidence
- `fail`: one or more required assertions failed
- `blocked`: the evaluator could not judge reliably because of environment limits, unclear target behavior, or missing evidence

When a case is `blocked`, include `blocked_reason` with one of:

- `environment`
- `unclear-rule`
- `insufficient-evidence`

Only use statuses allowed by `targets/<target_id>/target.yaml`.

## Evidence Policy

Preferred evidence:

- the accepted fresh-agent evidence captured from the active runtime
- the accepted final answer extracted from that evidence
- runtime-native session or task-process locator metadata

Supported runtime patterns:

- Codex mode:
  - spawn with `spawn_agent`
  - locate evidence from `~/.codex/sessions/`
  - use `~/.codex/state_5.sqlite` only as a locator or tie-breaker when needed
  - direct-process mode may run one fresh `codex exec --json` task process per isolated case; its redacted event trace and final answer are accepted evidence
- OpenClaw mode:
  - spawn with `sessions_spawn`
  - retrieve evidence from `sessions_history`
  - use returned child session keys or labels as the primary locator

The accepted fresh-agent evidence is the authoritative evidence source for the current framework.
`transcript.md` is a derived human-readable view of that accepted session evidence.
Do not mark a case `pass` from a generic assistant claim such as "I checked the skill" unless the accepted session evidence shows what was actually read or run.

Static reads by the evaluator are allowed for:

- loading the repo contract
- understanding a case
- understanding the target skill after the fresh-agent run
- mapping failures to likely fix files

Static reads by the evaluator are not enough on their own to mark a dynamic case `pass` when a fresh-agent run was available.

If the runtime evidence source is unavailable, if the accepted fresh-agent evidence cannot be retrieved, or if the evidence is too coarse to support the assertion, do not judge the case as `pass`.
Mark the case `blocked` with:

- `environment` when the runtime evidence source is unavailable
- `insufficient-evidence` when the session exists but cannot support a reliable judgment

Invalid attempts can explain `notes`, but they cannot satisfy assertions or justify a `pass`.

## Workspace Isolation

Each case must run in its own fresh isolated workspace.

Rules:

- Do not execute cases directly in the user's main workspace.
- Create a new case workspace under `case_workspace_root` for every case.
- Apply case `setup` mutations only inside that case workspace.
- No case may observe filesystem mutations left by a previous case unless the current case setup explicitly recreates them.
- Preserve the accepted case workspace at least until `case-results/<case_id>.json` and `report.md` are written. Cleanup after reporting is optional.
- Judge isolation from observed session evidence, not from fresh-agent self-reporting.
- For both Codex and OpenClaw spawned-subagent evidence, treat per-tool `workdir` values, resolved read/write paths, and command-derived cwd outputs as authoritative isolation signals.
- Do not treat top-level session cwd metadata as authoritative isolation evidence by itself, because spawned child-session metadata may inherit the parent workspace cwd.
- Treat any observed access outside the case workspace as invalid evidence for that attempt.
- If no reliable per-tool workdir, resolved path, or command-derived cwd can be observed, that evidence cannot justify a `pass`.

The same isolation policy applies inside `ab-urls`.
Only the variant-local source workspace for that side may be used to create case workspaces.

## Assertion Contract

Cases may include:

- optional `assert.summary` as a short human-readable description of the protected behavior
- optional per-assertion `description` to explain the intent of that single check
- optional per-assertion `evidence_scope` to hint which accepted artifact file the evaluator should rely on, such as `accepted-session.json` or `final-answer.txt`

These human-readable fields are the assertion contract.
Older requirements should be written in terms of consultation, observed commands, ordering, and final answers, not idealized runtime-native events.

### Assertion Entry

Use this shape for every required or forbidden assertion.

Fields:

- optional `description`
- `pass_criteria`
- optional `fail_signals`
- optional `evidence_scope`

The evaluator must judge the check from the accepted session evidence and the accepted final answer.
Pass only when the available evidence satisfies the pass criteria and does not show any fail signal.
If the accepted session evidence does not support a reliable answer, mark the assertion `blocked`.

## Case Result Shape

Each `case-results/<case_id>.json` file must contain:

```json
{
  "case_id": "example-case",
  "workspace_root": "/tmp/skill-eval/run-123/example-case",
  "thread_id": "optional-thread-id-or-null",
  "session_path": "openclaw-session://child-session-key or /Users/name/.codex/sessions/...jsonl",
  "status": "pass",
  "blocked_reason": null,
  "assertions": [
    {
      "summary": "Consulted the top-level skill instructions before answering.",
      "status": "pass",
      "evidence": [
        "case-artifacts/example-case/accepted-session.json#msg-12"
      ]
    }
  ],
  "notes": ["Short explanation."],
  "suggested_fix_files": [".agents/skills/<target_id>/SKILL.md"]
}
```

Prefer `accepted-session.json#msg-<n>` references in `evidence` when the accepted session artifact is normalized into message records.
If the runtime only exposes stable line-oriented evidence, `accepted-session.json#L<line>` is also acceptable.
Use `transcript.md#L<line>` only as a readability aid.

## Comparison Shape

`comparison.json` for `ab-urls` should contain:

- `run_mode` with value `ab-urls`
- `target_id`
- `status` with a top-level run state such as `completed`, `partial`, or `blocked`
- `variant_a` and `variant_b`, each with:
  - `label`
  - `source_url`
  - `run_dir`
  - acquisition and run status summary
- `summary`
- `cases`

Each comparison case entry should contain:

- `case_id`
- `status_a`
- `status_b`
- `comparison`
- `notes`

Recommended `comparison` values:

- `same-pass`
- `same-fail`
- `same-blocked`
- `regression`
- `improvement`
- `behavior-change`
- `environment-divergence`

The comparison must join only on the same `case_id`.

## Report Shape

For `single-run`, `report.md` must contain exactly these sections:

1. `Run Summary`
2. `Case Table`
3. `Failures`
4. `Suggested Next Fixes`

For `ab-urls`, the top-level `report.md` must contain exactly these sections:

1. `Comparison Summary`
2. `Variant Table`
3. `Case Matrix`
4. `Regressions`
5. `Improvements`
6. `Suggested Next Fixes`

Keep `Suggested Next Fixes` to at most 3 items and point to real files.


## Evaluation Modes

Evaluations are a higher-level orchestration layer above targets and cases.
They define **how** to run tests (AB, comparison, subjective), not **what** to test.

### Modes

| Mode | Purpose | Variants | Output |
|------|---------|----------|--------|
| `ab` | Compare two versions of the same skill on the same cases | 2 (a, b) | Win/loss/tie per case + rubric scores |
| `comparison` | Compare different vendors' skills on shared cases | 2+ | Side-by-side rubric scores + ranking |
| `subjective` | Score a single skill on rubric dimensions beyond pass/fail | 1 | Per-case rubric scores |

### Evaluation YAML Shape

Every evaluation file must contain:

- `eval_id`: unique identifier
- `mode`: one of `ab`, `comparison`, `subjective`
- `title`: human-readable description
- `rubric`: path to a rubric YAML file

Mode-specific fields:

- `ab` and `comparison`: `variants` object with labeled skill paths or target IDs
- `ab`: `target_id` and `suites` (both variants share the same cases)
- `comparison`: `shared_cases.from_target` and `shared_cases.suites`
- `subjective`: `target_id` and `suites`

### Rubric Shape

Each rubric file must contain:

- `rubric_id`: unique identifier
- `dimensions`: array of scoring dimensions

Each dimension must contain:

- `name`: short identifier (e.g., `accuracy`, `safety`)
- `description`: what the dimension measures
- `scale`: array of valid scores (e.g., `[1, 2, 3, 4, 5]`)
- `anchors`: optional map of score → description for calibration

### Evaluation Workflow

1. Read this file.
2. Read the evaluation YAML from `evaluations/<mode>/<eval_id>.yaml`.
3. Read the referenced rubric from `rubrics/`.
4. Resolve the target(s) and case set.
5. For each variant:
   a. Prepare the skill version or skill path in the case workspace.
   b. Execute each case using the standard case execution chain.
   c. Collect evidence and judge pass/fail assertions as usual.
   d. Score each rubric dimension from the accepted session evidence.
6. Write variant-specific artifacts under `runs/<run_id>/variants/<variant_label>/`.
7. Write `eval-report.md`.

### Evaluation Run Artifacts

```text
runs/<run_id>/
├── manifest.json
├── variants/
│   └── <variant_label>/
│       ├── case-artifacts/
│       │   └── <case_id>/
│       │       ├── accepted-session.json
│       │       └── final-answer.txt
│       ├── case-results/
│       │   └── <case_id>.json
│       └── transcript.md
├── eval-report.md
└── report.md
```

`manifest.json` must additionally record:

- `eval_id`
- `eval_mode`
- `variant_labels`
- `rubric_id`

### Evaluation Case Result Shape

Each variant's `case-results/<case_id>.json` extends the standard case result with:

```json
{
  "case_id": "example-case",
  "variant": "a",
  "status": "pass",
  "assertions": [ ... ],
  "rubric_scores": {
    "accuracy": 4,
    "completeness": 5,
    "doc_consultation": 3,
    "safety": 5,
    "flow_adherence": 4
  },
  "rubric_notes": {
    "doc_consultation": "Consulted README but skipped quickstarts.md."
  }
}
```

### Evaluation Report Shape

`eval-report.md` must contain exactly these sections:

1. `Evaluation Summary` — mode, variants, case count, rubric used
2. `Scoring Table` — each case × each dimension, columns per variant
3. `Head-to-Head` — (AB and comparison only) win/loss/tie counts per dimension
4. `Detailed Findings` — per-case narrative of notable differences or quality issues
5. `Recommendations` — at most 3 actionable items pointing to real files

For `subjective` mode, omit the `Head-to-Head` section.

### Scoring Rules

- Score each dimension independently from the accepted session evidence.
- Use the rubric anchors for calibration. A score of 3 means "meets the anchor description for 3."
- If evidence is insufficient to score a dimension, record `null` and explain in `rubric_notes`.
- Rubric scores are independent of pass/fail assertions. A case can `pass` all assertions but score low on `completeness`, or `fail` an assertion but score high on `accuracy`.
- For AB and comparison modes, score each variant independently before comparing. Do not let one variant's score influence another's.
