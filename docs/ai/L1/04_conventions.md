# 04 Conventions

> Conventions for authoring targets, suites, cases, and evaluator-aligned docs in this repo.

## YAML Authoring Rules

- Keep YAML fields stable: `case_id`, `title`, `input`, `setup`, `assert`, `notes`
- Keep `suite.yaml` as the only activation list for runnable cases
- Use explicit case file paths in suite lists
- Keep `allowed_statuses` aligned with evaluator output values

## Case Design Principles

- One behavior rule per case when possible
- Assertions should be evidence-backed and observable
- Prefer precise pass/fail signals over broad prose
- Include why-it-matters notes for maintainers

## Evidence Conventions

- Prefer accepted child session artifacts as primary source
- Treat self-reported traces as low confidence only
- Require evidence scopes like `accepted-session.json` or `final-answer.txt`
- Mark uncertain evaluations as `blocked`, not pass/fail guesses

## Naming and Organization

- Case IDs are lowercase kebab-case with meaningful behavior names
- Suites are thematic (`bootstrap`, `routing`, `workflow`)
- Keep case files colocated with suite file for readability

## Script Conventions

- Runtime scripts write JSON artifacts under `case-results/`
- Report builder computes aggregate pass/fail/blocked counts
- Keep side effects confined to `RUN_DIR` output tree
- Parse evaluator outputs defensively (JSON fences, raw JSON objects)

## Git Conventions Used In This Repo

- Commit style: `type: description` or `type(scope): description`
- Branch style: `type/short-description`
- Common docs change prefixes: `docs:` or `docs(ai):`
- Avoid bypassing hooks with `--no-verify`

## Case Assertion Writing Patterns

- Required assertions should state expected evidence signals explicitly
- Forbidden assertions should describe concrete anti-signals, not broad intent
- Keep assertion language tool-agnostic; tie to artifacts and observed behavior
- Prefer one assertion per verifiable behavior to reduce ambiguous failures

## Review-Safe Editing Patterns

- Edit case and suite files together when activation changes
- Keep target-level changes separate from runtime script changes when possible
- Use small diffs for contract documents (`AGENT.md`, `docs/session-evidence.md`)
- Re-run parse and coverage checks after each logical edit cluster

## Documentation Conventions

- Preserve existing docs; add `docs/ai/` as an additive layer
- Keep L0 concise and structured
- Keep L1 files scannable and linked to L2 only when deeper detail is needed
- Keep last-reviewed dates explicit (`YYYY-MM-DD`)

## Review Expectations

- Validate YAML parse after edits
- Validate suite coverage (missing/duplicate references)
- Validate links in docs/ai
- Confirm changes are reflected in `docs/ai/test-results.md` when test workflow is run

## Anti-Patterns To Avoid

- Conflating evaluator implementation behavior with target contract behavior
- Writing assertions that depend on incidental log text
- Introducing undocumented status values in case result files
- Treating unresolved evidence ambiguity as a pass

## Related Deep Dives

- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Operational convention details for per-case attempts.
- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime output normalization conventions.
