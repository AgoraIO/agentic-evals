# 05 Workflows

> Step-by-step workflows for common repository tasks: adding cases, updating targets, and validating docs/contracts.

## Workflow: Add a New Case

1. Pick target and suite (for example `targets/agora/cases/workflow/`)
2. Create `<case_id>.yaml` with required sections
3. Add the case path to the suite's `cases` list in `suite.yaml`
4. Run YAML parse validation command
5. Run suite coverage command to ensure no missing/duplicate references
6. Update docs if behavior expectations changed

## Workflow: Modify Target Defaults

1. Edit `targets/<target_id>/target.yaml`
2. Update `default_suites`, `focus_areas`, or `allowed_statuses` as needed
3. Validate YAML
4. Re-check impacted suite files and case references
5. Note downstream impact in docs where needed

## Workflow: Run Validation for Target Data

1. Set `TARGET_ID`
2. Run parse validation command
3. Run suite coverage command
4. Resolve all parse, duplicate, or missing reference issues
5. Re-run both commands until clean

## Workflow: Update an Existing Case Safely

1. Read the current case and referenced suite
2. Identify whether change is behavioral or editorial
3. Keep `case_id` stable unless introducing a net-new behavior guard
4. Update `assert.required` and `fail_signals` with concrete evidence language
5. Re-run parse and coverage checks
6. Update docs if the expected behavior path changed

## Workflow: Generate Eval Report From Case Results

1. Ensure `RUN_DIR` exists and has `case-results/*.json`
2. Run `python3 scripts/generate_report.py`
3. Confirm `report.md` and `manifest.json.result_counts` updated
4. Inspect assertion detail rendering for readability

## Workflow: Update Progressive Disclosure Docs

1. Update affected files in `docs/ai/L1/` and `docs/ai/L1/L2/`
2. Keep L0 identity and index accurate
3. Re-run structural checks from `docs/workflows/test.md` guidance
4. Add or update `docs/ai/test-results.md`

## Workflow: A/B Evaluation Setup (Definition Layer)

1. Create `evaluations/ab/<eval_id>.yaml`
2. Reference existing targets and suites
3. Ensure both variants resolve to same case set
4. Use evaluator that supports `ab-urls` run mode
5. Inspect top-level comparison artifacts for completeness

## Workflow: Review Runtime Script Changes

1. Confirm contract compatibility with `AGENT.md`
2. Ensure result JSON keeps valid statuses and assertion list shape
3. Verify `workspace_root` and timing fields remain intact where expected
4. Run `scripts/generate_report.py` against sample case results if available
5. Update L2 runtime docs when parser or orchestration behavior changes

## Escalation Rules For Blocked Cases

- Use `blocked` when evidence cannot be reliably judged
- Set explicit `blocked_reason` categories where contract expects them
- Do not convert uncertain cases to `fail` without evidence

## Workflow Outputs To Preserve

- `manifest.json` should remain machine-readable and contract-aligned
- `case-results/*.json` should stay deterministic for downstream processing
- `transcript.md` should be derived from accepted evidence, not freehand notes

## Related Deep Dives

- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime execution workflow details.
- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Workspace-attempt and isolation workflow details.
