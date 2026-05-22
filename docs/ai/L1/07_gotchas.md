# 07 Gotchas

> Critical pitfalls and operational lessons that commonly cause invalid evaluations or misleading results.

## Contract Drift Risks

- Editing runtime scripts without updating contract docs can break artifact assumptions
- Adding statuses not listed in `allowed_statuses` creates mismatch
- Treating suite files as assertion sources causes semantic drift (case files own assertions)

## Evidence Pitfalls

- Relying on self-reported trace text is low confidence
- `session_meta.cwd` can be misleading for spawned child sessions
- Missing accepted child session linkage should result in `blocked`
- Guessing file paths from incomplete shell output creates false positives

## Workspace Isolation Traps

- Commands may run with parent cwd if workspace setup fails
- Relative path parsing in command analysis can misclassify out-of-workspace access
- Absence of `workdir` observations weakens isolation confidence

## YAML and Suite Integrity Traps

- Case file added but not referenced in any suite
- Duplicate case references in suite lists
- Parse-valid YAML that still violates expected contract shape
- Inconsistent case IDs between filename and `case_id` value

## Runtime-Specific Traps

- CLI availability differences across local and CI environments
- Timeout behavior can produce incomplete evaluator JSON
- Model output may include fenced markdown around JSON; parser must handle both
- Failure to parse evaluator JSON should produce deterministic blocked output

## Reporting Traps

- Report generation can silently succeed with zero cases if `case-results/` is empty
- Partial case result fields can degrade report readability without failing generation
- Inconsistent status casing can skew aggregate counts
- Missing `manifest.json` fields reduce post-run traceability

## Documentation Traps

- L0 growing into prose-heavy content instead of identity + index only
- L1 files missing `Related Deep Dives` section
- Broken relative links across `docs/ai/` tree
- Outdated `Last Reviewed` dates reducing trust

## Mitigations

- Re-run parse and suite coverage checks after every target/case edit
- Keep evidence contract updates synchronized with script changes
- Keep runtime quirks documented in L2, not hidden in ad-hoc notes
- Re-test docs with realistic questions after major contract edits

## Quick Triage Sequence

1. Confirm target/suite/case YAML parse cleanly
2. Confirm suite references are complete and deduplicated
3. Confirm runner output includes valid `case-results/*.json`
4. Confirm report summary matches per-case statuses
5. Confirm evidence artifacts exist for each judged case

## Escalation Clues

- Repeated parse failures on the same case usually indicate malformed YAML structure, not runtime issues
- Frequent blocked outcomes with missing evidence may indicate child-session locator regressions
- Sudden report count mismatches usually point to malformed or missing case-result files
- Large variance across runtimes on identical cases may indicate runner parser drift

## Fast Sanity Checks

- Confirm `allowed_statuses` in target files still include only expected values
- Confirm every newly added case path appears exactly once in a suite file
- Confirm deep-dive links in L1 remain valid after file renames

## Related Deep Dives

- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Detailed isolation and workspace-failure handling.
- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime-specific parsing and failure behavior.
