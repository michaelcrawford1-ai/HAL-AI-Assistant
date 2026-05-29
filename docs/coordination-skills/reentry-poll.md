# Re-entry Poll Doctrine

Public portfolio version. This document is a sanitized design artifact, not an operational runbook.

## Purpose

The re-entry poll is the mechanism that brings the architect lane back into a multi-agent sprint after an implementation or review lane completes its turn.

Without a re-entry mechanism, the user becomes the courier between AI tools. The poll reduces that manual coordination burden while preserving review gates and human approval for high-impact decisions.

## Core doctrine

```text
Project issue state is the source of truth.
Notification tools are transport surfaces only.
The architect lane re-enters by reading the canonical issue, labels, and latest results.
The architect lane does not manually operate the notification surface as a substitute for the relay.
Implementation and review lanes post results back to the canonical issue.
```

## Trigger concept

A scheduled or event-driven re-entry process checks for work items that indicate the architect lane is needed again.

Typical triggers include:

| Trigger | Meaning |
|---|---|
| Implementation complete | Code lane finished a bounded task and posted results. |
| Review complete | Review lane posted approval, concerns, or requested changes. |
| Decision required | A stop condition or unresolved tradeoff requires architect or human synthesis. |
| Budget exceeded | A lane hit its time, turn, or failure budget and needs a decision. |
| Blocked | Required access, configuration, or prerequisite state is missing. |

## Re-entry behavior

When re-entry is triggered, the architect lane should:

1. read the canonical work item;
2. read the latest implementation or review result;
3. verify the result against the original handoff and acceptance criteria;
4. check whether any stop condition was triggered;
5. decide the next state;
6. produce exactly one next action.

Possible next actions:

| Outcome | Next action |
|---|---|
| Complete | Mark the work complete and summarize evidence. |
| Partially complete | Draft the next bounded handoff. |
| Needs review | Route to review lane. |
| Blocked | Produce a decision packet or unblock request. |
| Unsafe or unclear | Pause and request human decision. |

## Authority boundaries

The re-entry process may perform coordination actions that are explicitly in scope, such as:

- reading issues, pull requests, and review results;
- posting architect verdict comments;
- preparing the next handoff;
- applying scoped coordination labels when authorized;
- creating or updating documentation in a normal reviewable branch.

It may not:

- manually post as the user in notification tools;
- deploy services;
- restart production systems;
- access credentials;
- mutate external systems;
- run uncontrolled implementation work;
- bypass human approval for safety-sensitive action.

## Notification surface boundary

The notification surface should only announce that work changed state. It should not become the source of truth.

Correct shape:

```text
Architect updates canonical issue state
→ relay emits notification
→ implementation or review lane works from the issue
→ lane posts results to the issue
→ re-entry process detects architect-needed state
→ architect renders verdict from the issue
```

Incorrect shape:

```text
Architect manually clicks notification surface
→ posts as the user
→ downstream tools react to an out-of-band message
→ canonical issue state becomes stale or ambiguous
```

The second pattern is intentionally prohibited because it creates silent skips, duplicate work, and unclear authority.

## Local handoff artifact availability

Some workflows use local handoff documents as execution payloads for downstream agents. Those files are useful but are not automatically durable project state unless committed or summarized in the canonical issue.

If a re-entry session cannot access a local handoff document, it should:

1. state that the handoff file is unavailable;
2. fall back to the issue body, dispatch record, latest comments, pull requests, and commits;
3. avoid claims that depend on unread local handoff content;
4. pause if the missing handoff blocks a safe verdict.

## Safety and decision handling

A re-entry pass should pause rather than improvise when it sees:

- live-system mismatch;
- missing verification evidence;
- failed tests without clear resolution;
- a security or credential surface;
- physical-world or external-impacting action;
- ambiguous ownership;
- conflicting instructions between chat, issue, and repository state.

## Poll latency and limitations

A scheduled poll may introduce latency. That is usually acceptable because the goal is reliable handoff, not instant chat response.

Known limitations to design around:

- polling can miss work if labels or issue state are wrong;
- repeated triggers can occur if completed work is not closed or relabeled;
- local handoff files may not be available to every session;
- notification messages can be truncated;
- human approval is still required for high-impact decisions.

## Public portfolio note

The private operational version may reference concrete task names, labels, channels, and local automation. Those details are intentionally removed here. This public version documents the governance pattern: scheduled re-entry, canonical state, bounded authority, and no manual notification-surface bypass.