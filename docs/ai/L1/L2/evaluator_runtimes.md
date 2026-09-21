# Evaluator Runtimes

> **When to Read This:** Load this document when changing runtime runner scripts, output parsing, or cross-runtime artifact normalization.

## Overview

The repository supports multiple runtime-specific runners while enforcing a common contract.

- OpenClaw-oriented runner
- Gemini two-phase runner
- Hermes runners including sub-agent orchestration
- Shared report generation and artifact expectations

## Common Two-Phase Pattern

1. Task phase generates candidate answer and workspace effects
2. Evaluation phase judges assertions and writes structured result JSON

All runners should preserve `pass`/`fail`/`blocked` semantics and case artifact outputs.

## Direct Task Runner Evidence

- Credential-write provenance uses in-memory snapshots taken immediately before
  and after the task process, before starting verification. New or changed env
  files in the detected quickstart must contain both required non-placeholder
  Agora keys. Both `.env` and `.env.local` in the detected quickstart are
  recorded independently. Snapshots establish file-write provenance; credential
  and runtime assertions still require independent verification. This covers
  CLI, shell, and editor writes without trusting command text or pre-existing files.
- Snapshots exclude dependency directories and symlinks. Credential values and
  fingerprints are never persisted; artifacts contain only the resulting facts.
- Reports accept both `summary`/`evidence` and `description`/`notes` assertion
  fields, preserving explanations without changing pass/fail/blocked results.

## OpenClaw Runner Notes

- Uses `acpx openclaw` for task execution
- Can run evaluator phase via `codex exec` with gateway override
- Handles NDJSON extraction for text and tool events
- Requires robust JSON judgment extraction because output formats vary

## Gemini Runner Notes

- Uses `gemini --yolo --output-format json`
- Writes task and evaluator raw outputs per case
- Uses defensive JSON extraction from fenced or inline responses
- Falls back to `blocked` on parse failure

## Hermes Runner Notes

- The task stderr's exact `session_id` selects a redacted JSONL session export.
  Tool calls and results are saved in `task-session.json` before verification;
  the verifier reads this file and correlates call IDs with successful results.
  Missing, ambiguous, or mismatched sessions remain unavailable; the runner
  never falls back to the latest session. Timeout output is preserved for lookup.
- Invite verification uses `network requests --json`, then
  `network request <request-id> --json` for the POST made by the browser click.
  Plain output may contain only the URL; no extra POST is sent for proof.


- Supports evaluator+subagent orchestration
- Main evaluator prompt instructs sub-agent to execute task in workspace
- Evaluator then independently verifies workspace state
- Includes server warm-up and verification guidance in prompts for web tasks
- For the ConvoAI Next.js E2E case, collects a bounded GET probe for `/`,
  records disabled pnpm build scripts, and copies available agent-created
  install/dev logs into the artifact directory.
- Runtime artifacts redact Agora credential values before persistence. HTTP
  response bodies are measured but not stored.

## Artifact and Field Normalization

Across runtimes, scripts should produce:

- `case-results/<case_id>.json` with status and assertions
- `case-artifacts/<case_id>/final-answer.txt`
- optional runtime-specific raw evidence files

Useful normalized fields include timing and `workspace_root`.

## Failure Handling

- Parsing failures map to `blocked` with explicit reason notes
- Missing session linkage or ambiguous evidence maps to `blocked`
- Timeout conditions should be preserved in notes for auditability

## See Also

- [Back to Architecture](../02_architecture.md)
- [Back to Interfaces](../06_interfaces.md)
- [Back to Security](../08_security.md)
