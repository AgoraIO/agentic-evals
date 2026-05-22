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

- Supports evaluator+subagent orchestration
- Main evaluator prompt instructs sub-agent to execute task in workspace
- Evaluator then independently verifies workspace state
- Includes server warm-up and verification guidance in prompts for web tasks

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
