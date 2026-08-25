# Session Evidence Contract

This document defines the evidence sources used by `agentic-evals`.

The evaluator supports two runtimes:

- Codex local session store
- OpenClaw session history

The evaluator should pick the runtime that is actually available in the current environment and record it in `manifest.json.evidence_mode`.

## Primary Sources

Use these sources in priority order:

- accepted fresh-agent evidence from the active runtime
- accepted final answer extracted from that evidence
- runtime-native session or task-process locator metadata

Per runtime:

- Codex spawned mode:
  - accepted child session under `~/.codex/sessions/`
  - `spawn_agent` success metadata such as nickname or returned id
  - `~/.codex/state_5.sqlite` only to locate and disambiguate child threads
- Codex direct-process mode:
  - redacted `codex exec --json` event trace and task final answer stored in the case artifact directory
- OpenClaw:
  - accepted child session returned by `sessions_history`
  - `sessions_spawn` success metadata such as the returned child session key or label

Do not treat the fresh agent's self-reported `TRACE_FILES_READ` or `TRACE_COMMANDS_EXECUTED` as authoritative evidence.
They may appear in older child sessions, but they are only low-confidence supporting notes.

## Evidence Location

For spawned sessions, the evaluator should identify the accepted child session by combining:

- runtime-native spawn metadata
- child start time relative to the case attempt
- thread title, nickname, or label as tie-breakers when the runtime exposes them
- child session cwd metadata only as a low-confidence locator, because spawned child sessions may inherit the parent thread cwd in metadata

Per runtime:

- Codex spawned mode:
  - `spawn_agent` success metadata such as nickname or returned id when available
  - child session `session_meta.payload.source.subagent.thread_spawn.parent_thread_id`
  - `~/.codex/state_5.sqlite` `thread_spawn_edges` when available
- Codex direct-process mode:
  - retain the task process event trace and final answer under that case's artifact directory
- OpenClaw:
  - the `childSessionKey` returned by `sessions_spawn`
  - returned label or metadata when available

If spawned-mode evidence cannot be matched to a single child session, or direct-process evidence is missing, mark the case `blocked`.

## What To Extract From Session Evidence

The evaluator may use these session item types after adapting the runtime-specific payload into a common judgment model:

- `session_meta`
- `event_msg.user_message`
- `event_msg.agent_message`
- `event_msg.task_started`
- `event_msg.task_complete`
- `response_item.function_call`
- `response_item.function_call_output`
- `response_item.message`

These records are sufficient to judge many cases because they expose the child prompt, tool calls, tool outputs, and final answer.

Runtime notes:

- Codex evidence may originate as JSONL and should be normalized into `accepted-session.json` when practical.
- OpenClaw evidence may come directly from `sessions_history(..., includeTools=true)`.

## Extraction Rules

- Convert `session_meta` into `session_start`.
- Convert `task_complete` into `session_end`.
- Convert `response_item.function_call` into `tool_call`.
- Convert `response_item.function_call_output` into `tool_result`.
- When a tool call includes `workdir`, emit `tool_workdir_observed`.
- When a tool result shows an executed shell command, emit `command_observed`.
- When a command clearly reads a file, emit `file_read_observed`.
- When a command or patch clearly writes a file, emit `file_write_observed`.
- Convert the accepted child-session final assistant output into `final_answer`.

For shell-derived file observations, prefer stable patterns such as:

- `sed -n ... <path>`
- `cat <path>`
- `nl -ba <path>`
- `rg ... <path>`
- `find ...`

If a path cannot be reconstructed reliably, do not invent one.

## Isolation Rules

Judge isolation only from observed evidence.

- Prefer per-tool `workdir` values and command-derived paths as the authoritative isolation signals
- Treat `session_meta.cwd` as advisory only for spawned-subagent runs, because it may remain equal to the parent thread cwd even when the child agent's tool calls stay inside the case workspace
- observed per-tool `workdir` values must stay inside the accepted case workspace
- observed read and write paths must stay inside the accepted case workspace
- if a command such as `pwd` prints a cwd, that observed cwd must stay inside the accepted case workspace
- if observed paths leave the case workspace, emit `isolation_violation`
- do not treat `session_meta.cwd` alone as an isolation violation when all observed tool workdirs and resolved paths stay inside the accepted case workspace
- if no reliable tool workdir, resolved path, or command-derived cwd can be observed, that evidence cannot justify a `pass`

## Artifact Expectations

The evaluator should preserve:

```text
case-artifacts/<case_id>/
├── accepted-session.json
└── final-answer.txt
```

`accepted-session.json` is the accepted fresh-agent evidence artifact for the active runtime.
It may be:

- a normalized JSON rendering of Codex session JSONL, or
- a copied or normalized OpenClaw `sessions_history` result

## Transcript Rendering

`transcript.md` should be rendered directly from the accepted session evidence, with references back to the accepted session when useful.

It should:

- preserve accepted event order
- identify the thread id and session path
- remain clearly derivative of accepted session evidence
