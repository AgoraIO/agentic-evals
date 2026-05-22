# Case Workspace Lifecycle

> **When to Read This:** Load this document when changing case workspace creation, isolation validation, or accepted-session selection logic.

## Overview

Each case should run in its own fresh workspace attempt to prevent cross-case contamination.

## Lifecycle Steps

1. Resolve case and target context
2. Create case workspace (often under `/tmp/.../<case_id>/attempt-XX`)
3. Copy or prepare required `.agents/skills` and reference files
4. Execute task phase inside workspace
5. Collect accepted session evidence and final answer
6. Run evaluation and write case result JSON

## Isolation Expectations

- Observed `workdir` values should remain inside workspace root
- Observed file reads/writes should remain inside workspace root
- `session_meta.cwd` is advisory only and may reflect parent thread context
- Lack of reliable evidence should not be treated as clean isolation

## Accepted Session Selection

Preferred signals:

- runtime-native spawn metadata
- attempt timing correlation
- thread labels or IDs
- command/workdir observations

If reliable matching is impossible, mark case `blocked`.

## Artifact Expectations Per Case

```text
case-artifacts/<case_id>/
├── accepted-session.json
└── final-answer.txt
```

`accepted-session.json` should be the authoritative trace used for judgment and transcript rendering.

## Common Failure Modes

- Workspace setup script fails and runner silently falls back to a broader cwd
- Missing `.agents` content causes routing failures unrelated to target behavior
- Evidence paths cannot be resolved due to incomplete command capture
- Out-of-workspace access observed but not surfaced as isolation violation

## Hardening Guidelines

- Validate workspace path existence before task phase
- Capture `workdir` and command outputs whenever available
- Keep parser rules explicit and conservative for file-path extraction
- Prefer false-negative pass avoidance (`blocked`) over false-positive pass

## See Also

- [Back to Setup](../01_setup.md)
- [Back to Gotchas](../07_gotchas.md)
- [Back to Security](../08_security.md)
