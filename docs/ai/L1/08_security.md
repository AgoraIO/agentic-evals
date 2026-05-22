# 08 Security

> Security model for isolated evaluations, trust boundaries, and sensitive data handling in this repo.

## Security Goals

- Keep per-case execution isolated
- Prevent accidental leakage of credentials into artifacts
- Preserve evidence integrity for judgment
- Maintain clear trust boundaries between agent output and authoritative evidence

## Trust Boundaries

- Target definitions (`targets/`) are trusted contract inputs
- Runtime tool outputs are observational data, not truth by default
- Accepted session evidence is higher-trust than self-reported summaries
- Notification and external API calls are optional integration boundaries

## Secret Handling

- Never hardcode credentials in case files or docs
- Runtime scripts may consume env vars for endpoint/auth configuration
- `.env` style values should stay out of committed artifacts
- Reports should summarize status, not expose secrets

## Isolation Controls

- Each case runs in an isolated workspace attempt
- Evidence extraction prefers observed `workdir` and resolved paths
- Out-of-workspace reads/writes are isolation violations
- Missing reliable isolation signals should not pass by default

## Integrity Controls

- Case results are persisted as JSON for deterministic post-processing
- Reports are generated from case-results data, not ad-hoc terminal notes
- Manifest fields should capture run metadata and evidence mode
- `blocked` status protects against overconfident false judgments

## External Integration Risks

- Feishu notifications transmit summary data; avoid sensitive payloads
- External model gateways must be configured via env vars, not inline tokens
- CLI tooling differences across machines can alter observability depth

## Data Classification Guidance

- `targets/` and `evaluations/` are generally low sensitivity but contract-critical
- `case-artifacts/` may contain runtime outputs; treat as internal evaluation data
- `accepted-session.json` can include commands and paths; avoid sharing publicly without review
- Notification payloads should contain status summaries, not raw traces

## Safe Defaults

- Default to `blocked` when evidence confidence is low
- Default to redacting or omitting credentials from examples
- Default to local-relative path references in docs
- Default to minimal required external API payload content

## Review Checklist

- Are secrets absent from target and case YAML?
- Are isolation violations correctly surfaced as failures/blocked?
- Are evidence sources and transformations traceable?
- Are generated reports free of secret leakage?

## Incident Prevention Notes

- Keep endpoint and token configuration in env vars only
- Audit new scripts for accidental file writes outside `RUN_DIR`
- Keep trust-boundary docs current when adding new runtime integrations
- Validate that failure notes do not leak sensitive host or credential data

## Minimal Secure Change Process

1. Make the contract or script change
2. Re-run YAML integrity checks
3. Re-check for accidental credential literals in edited files
4. Validate generated reports contain no secret-bearing fields
5. Update security-relevant docs when trust boundaries changed

## Related Deep Dives

- [Case Workspace Lifecycle](L2/case_workspace_lifecycle.md) - Isolation controls and evidence chain details.
- [Evaluator Runtimes](L2/evaluator_runtimes.md) - Runtime-specific trust and parsing behavior.
