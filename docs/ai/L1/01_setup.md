# 01 Setup

> Environment setup, prerequisites, and quick validation commands for editing or running eval assets.

## Prerequisites

- macOS or Linux shell with `bash`, `ruby`, and `python3`
- Write access to the repo working tree
- Ability to run CLI tools used by optional evaluators (`codex`, `acpx`, `gemini`, `hermes`) when relevant
- Local clone includes `.agents/skills/` because targets reference those paths

## Quick Start

1. Open repo root: `agentic-evals/`
2. Read [AGENT.md](../../../AGENT.md) first for evaluator contract
3. Pick a target (default commonly `voice-ai-integration`)
4. Validate YAML parses before editing behavior

## Core Validation Commands

```bash
TARGET_ID=voice-ai-integration ruby -e 'require "yaml"; Dir["targets/#{ENV.fetch("TARGET_ID")}/cases/*/suite.yaml"].sort.each { |f| YAML.load_file(f) }; Dir["targets/#{ENV.fetch("TARGET_ID")}/cases/**/*.yaml"].sort.reject { |f| f.end_with?("suite.yaml") }.each { |f| YAML.load_file(f) }; YAML.load_file("targets/#{ENV.fetch("TARGET_ID")}/target.yaml"); puts "yaml-ok"'
```

```bash
TARGET_ID=voice-ai-integration ruby -e 'require "yaml"; target_id = ENV.fetch("TARGET_ID"); refs = Dir["targets/#{target_id}/cases/*/suite.yaml"].sort.flat_map { |f| YAML.load_file(f)["cases"] }; counts = Hash.new(0); refs.each { |r| counts[r] += 1 }; cases = Dir["targets/#{target_id}/cases/**/*.yaml"].sort.reject { |f| f.end_with?("suite.yaml") }; missing = cases.reject { |c| counts.key?(c) }; dupes = counts.select { |_, v| v > 1 }; puts "cases=#{cases.size} suite_refs=#{refs.size} dupes=#{dupes.size} missing=#{missing.size}"'
```

## Optional Runtime Commands

- Codex/OpenClaw eval path: `scripts/run_openclaw_eval.py`
- Gemini eval path: `scripts/run_gemini_eval.py`
- Hermes eval path: `scripts/run_hermes_eval.py` and `scripts/run_hermes_subagent_eval.py`
- Report generation: `RUN_DIR=<path> python3 scripts/generate_report.py`

## Tooling Checks

- Confirm Ruby exists for YAML validation:

```bash
ruby -v
```

- Confirm Python exists for script orchestration:

```bash
python3 --version
```

- Confirm target files are present before edits:

```bash
ls targets/agora/target.yaml targets/voice-ai-integration/target.yaml
```

## Required Environment Variables (by script)

| Variable | Used By | Purpose |
| --- | --- | --- |
| `RUN_DIR` | multiple scripts | Output artifact root for reports and case results |
| `TARGET_ID` | workspace setup and validation | Select target tree under `targets/` |
| `GEMINI_MODEL` | `run_gemini_eval.py` | Optional model override |
| `HERMES_MODEL` | hermes scripts | Optional model override |
| `RESPONSES_API_ENDPOINT` | OpenClaw evaluator | Override Codex gateway endpoint |
| `OPENAI_API_KEY` | OpenClaw evaluator | Auth for evaluator phase when needed |
| `FEISHU_APP_ID` and peers | `notify_feishu.py` | Notification integration |

## Setup Failures and Fixes

- YAML parse failure: re-run parse command and inspect the first file reported
- Missing suite linkage: run coverage command and add missing case paths to `suite.yaml`
- Missing `.agents` references in case workspace: verify `create_case_workspace.sh` inputs
- Missing runtime CLIs: use the runtime script only when that CLI is installed

## Pre-PR Validation Checklist

- Parse check returns `yaml-ok` for each touched target
- Coverage check reports `dupes=0` and `missing=0`
- Any changed contract wording is mirrored in `docs/ai/`
- If run artifacts are generated locally, keep them out of committed docs unless required

## Working Rules

- Treat `targets/<target_id>/target.yaml` as the contract anchor
- Keep edits minimal and traceable to a case assertion
- Preserve existing docs outside `docs/ai/`

## Related Deep Dives

- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime execution details and evidence outputs.
- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - How isolated per-case workspaces are created and judged.
