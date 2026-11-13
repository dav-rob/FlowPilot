# Finance workspace

The home page presents business cases grouped by document, with the standard
route and the human review route visible side by side. The inbox uses the supplied
250 example documents; opening a page never initiates model calls.

## Document and decision flow

1. Open **Documents**, read the correspondence and attachments, and select
   **Review document**. Original input goes unchanged to the shared AI engine.
2. Read **Findings, next steps** in **Cases & findings**. Routine reviews finish
   without opening unrelated approval workflows.
3. Explicit handoff outcomes open named departmental work items in **Approvals**.
   For example, `block_pending_privacy_assessment` holds the proposed contract or
   processing change for Privacy; other mentioned departments are not all added.
4. Reviewers enter a decision note and approve or decline. Departmental approval
   records a decision only. It does not amend a contract, change customer data,
   grant retrospective approval or execute a consequential action.
5. A consequential action is a separate proposal. Required departmental decisions
   must be approved before that proposal can execute. A declined departmental
   review also denies dependent pending action proposals. Identity, legal holds,
   retention, tool scope and exact action approval remain independently enforced.
6. **Open trace** from a business result opens its observability page: model and
   tool calls, timing, usage where reported, validation, handoffs, decisions and
   raw recorded data. No private model reasoning is claimed.

Approvals concern fictional state and are attributed to the local demo reviewer.
The app does not authenticate bank roles or implement production separation of
duties. Decisions, notes, timestamps and results persist in SQLite. Cancelling
an awaiting review denies its pending action and departmental requests. Saved
replays cannot make decisions.

## Case counts and earlier findings

Repeated checks are grouped by partition and case ID; identical custom inputs
use a content fingerprint. Latest findings supply the headline; earlier pending
action requests retain their exact execution links. Tests, scored evaluations and
simulations do not inflate business totals. Read-only recordings are a fallback
when an original review is absent.

At startup, the latest successful original business findings can be enrolled in
the current manual workflow. A new, timestamped handoff explicitly identifies
this origin. Historical trace events, timings and unknown rule versions are not
rewritten or credited as new AI execution. `review_execution_status` preserves
the previous completed state when enrolment creates a pending decision.

## Evals

**Evals** is available in normal navigation. Its first section explains actual AI
attempts, saved recordings, simulations, repeated documents and failures. The
Test Workbench follows that explanation. Subsections provide:

- Quality: scored evaluations, expected versus actual outcomes, evidence and tool
  coverage, models, durations and versions when recorded.
- Guardrails: readable rule/check/response/exception definitions and repeatable
  isolated runtime tests, including permitted actions as positive controls.
- Evolution: sourced development observations and append-only measured guardrail
  results, with test/rule versions and implementation fingerprints.
- Test workbench, execution history and tool registry for technical exploration.

New reviews and evaluations record application and ruleset versions. Earlier
versions remain unknown. Deterministic tests do not measure live AI performance
or comprehensive prompt-injection resistance. See [ASSURANCE.md](ASSURANCE.md).

Direct links include `#evals/guardrails`, `#evals/evolution`, `#evals/workbench`,
`#approvals` and `#trace/<execution-id>`. Old developer-opt-in links are preserved
as redirects into Evals. `?developer=true` remains a navigation preference, not
an authentication boundary. There is no connected mailbox, folder or webhook.
