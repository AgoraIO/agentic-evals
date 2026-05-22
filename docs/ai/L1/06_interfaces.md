# 06 Interfaces

> Boundary contracts between target definitions, evaluator scripts, and run artifacts.

## Contract Interfaces

| Interface | Source | Consumer |
| --- | --- | --- |
| Target contract | `targets/<target_id>/target.yaml` | Evaluator runtime scripts |
| Suite contract | `targets/<target_id>/cases/*/suite.yaml` | Case selection logic |
| Case contract | `targets/<target_id>/cases/*/<case_id>.yaml` | Execution + judgment logic |
| Evidence contract | `docs/session-evidence.md` | Session extraction + isolation checks |
| Rubric contract | `rubrics/default.yaml` | Subjective/comparison scoring layers |

## Target YAML Interface

Key fields:

- `target_id`
- `entry_skill`
- `roots`
- `default_suites`
- `suite_root`
- `artifact_contract.required`
- `allowed_statuses`

## Suite YAML Interface

- `suite_id`
- `cases` list with references to concrete case files
- suite remains an activation list, not behavior definition

## Case YAML Interface

Expected shape:

- `case_id`
- `title`
- `input`
- `setup`
- `assert.summary` (optional)
- `assert.required`
- `assert.forbidden`
- `notes`

## Runtime Artifact Interface

Expected single-run outputs:

- `manifest.json`
- `case-artifacts/<case_id>/accepted-session.json`
- `case-artifacts/<case_id>/final-answer.txt`
- `transcript.md`
- `case-results/<case_id>.json`
- `report.md`

## Case Result JSON Interface

Common fields observed:

- `case_id`
- `status` (`pass`, `fail`, `blocked`)
- `assertions`
- `notes`
- timing fields
- `workspace_root`

## External Tool Interfaces

- Feishu message API from `notify_feishu.py`
- Runtime CLIs (`codex`, `acpx`, `gemini`, `hermes`) invoked by scripts
- Filesystem interface for case workspace generation and evidence persistence

## Compatibility Rule

Runtime script differences are allowed if they preserve the contract-level artifact and status semantics.

## Related Deep Dives

- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime interface differences and normalization.
- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Workspace and evidence interface details.
