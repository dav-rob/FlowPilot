# Model integration

FlowPilot uses authenticated local subscriptions. It has no reasoning-model REST API or paid API fallback. Optional JEV classification uses TypeSafe's API separately.

## Routing

`ai-models.toml` defines ordered `screening`, `investigation`, and `escalated` roles. Each run snapshots the file before classification. Invalid configuration blocks new live calls while existing results remain readable.

- Screening: Antigravity Flash low, Claude Haiku low, Codex Luna low.
- Investigation: Antigravity Flash medium, Claude Haiku low, Codex Luna low. Medium was selected after actual low-effort investigations repeatedly returned inconsistent action envelopes.
- Escalated: Antigravity Argon high, Claude Sonnet high, Antigravity Sonnet high, Codex Sol high. Argon is first because a live Claude escalation probe emitted native enterprise tool-use blocks instead of the JSON protocol; the adapter correctly rejected that result. This explicit policy choice is distinct from automatic quota fallback.

Only an explicit usage/rate limit advances a role's provider chain. Limited routes enter a process-local cooldown using reported reset times where available, or the configured five-minute default. Authentication, missing binary, malformed output, timeout and unexpected CLI tool activity fail visibly. No account switching, credit purchase or quota reset is performed.

Business uncertainty or conflicting evidence can select the stronger role. This is separate from provider fallback. Semantic protocol errors (for example, `kind=calls` with an empty action array) are rejected before any tool dispatch; the engine allows at most two explicit corrections through the same model role, within the normal budgets. Uncorrected responses fail.

## Adapter interfaces

`ModelRouter.complete(role, system, payload, schema)` is asynchronous and returns `ModelResponse(data, provider, model, effort, usage, session_id, events)`. JSON Schema validation runs on returned data. Successful fallback and cooldown events accompany the response and enter the application trace. Provider usage counters are recorded when supplied; absent values remain unknown.

The provider adapters run blocking CLI processes in worker threads with explicit process-group deadlines, bounded output capture, and cancellation cleanup. They use disposable working directories outside this repository, with no dataset or ground-truth files. Public application traces exclude raw adapter transcripts and approval tokens.

### Antigravity

Verified version: `agy 1.5.3`.

A temporary `.agents/agents/screener.md` requests only the internal `finish` tool. The adapter supplies `--agent screener`, `--settings`, `--json-schema`, stream JSON input/output, and an explicit print timeout. Per-invocation settings set `toolPermission: strict`, terminal sandboxing, no non-workspace access, and deny rules for `read_file(*)`, `write_file(*)`, `read_url(*)`, `execute_url(*)`, `command(*)`, and `mcp(*)`.

Antigravity's `init.tools` reports its **session-wide registry**, including tools absent from the restricted agent. It cannot be interpreted as the effective agent allowlist. The adapter verifies strict permission mode, original working directory, terminal success, no denied actions, no external tool steps, and no new files. Only the internal structured-output `finish` step is accepted. This transport follows the existing JobGraph implementation. An unsafe or incomplete result is rejected.

Live Flash low and medium have been exercised, including the counterfactual branching test and complete showcase investigations. Model identity is taken from the initialization response; a mismatch with the requested model fails.

### Claude

Verified catalog: `claude 2.1.319`; Sonnet 5.5 and Haiku 5.5 support the selected effort levels in this account.

The adapter uses `--print`, exact model/effort, `--tools ""`, `--safe-mode`, `--no-session-persistence`, stream JSON output, `--json-schema`, and a system prompt. It removes `ANTHROPIC_API_KEY` from the child environment so subscription execution does not silently become a paid API call. It rejects unexpected available tools/MCP attachments or external tool use. Both terminal exit code and result fields must indicate success; a `success` subtype with `is_error: true` fails.

Claude returned an explicit subscription usage limit during initial development delegation. That event is not evidence that Claude's application adapter completed inference. A later live escalation probe returned native enterprise tool-use blocks rather than the structured action protocol and was rejected. The default stronger route therefore starts with Argon; Claude remains configurable. Normal quota fallback remains available.

### Codex

Verified catalog: `codex-cli 0.166.0`; account discovery uses the app-server `model/list` protocol and supported efforts.

The adapter uses ephemeral execution, an empty working directory, read-only sandbox, no user configuration/rules, disabled tool-related features, and a temporary copy of the CLI model catalog with tools disabled. It does **not** alter the installed CLI or global model configuration. A `debug prompt-input` preflight uses a disposable empty `CODEX_HOME` and verifies that no execution-capable tools are offered. The actual completion retains the existing subscription authentication location while ignoring user configuration. Any command/tool event on the JSONL stream stops execution. Strict schema, terminal-event and exit-status checks apply.

Catalog discovery and fake-parser tests are covered. A successful live FlowPilot business investigation through this adapter has not yet been established; default showcase runs use Antigravity. Unsupported future CLI flags or catalog changes fail visibly rather than weakening restrictions.

## Classification

`classify(document, mode, router)` returns primary and multiple categories, uncertainty, risk, urgency, escalation reason and actual provider/model identity.

- Simulation uses an explicitly labelled keyword heuristic, `confidence: null`, and no model or JEV call.
- Live mode with no JEV key uses the configured CLI screening route and labels the decision as CLI classification.
- Live mode with `TYPESAFE_API_KEY` or `JEV_API_KEY` calls [TypeSafe System One](https://docs.typesafe.ai/api/system-one): `POST https://api.typesafe.ai/v1/systemone`, bearer authentication, `model`, `state`, and typed `questions`. Choice determines primary category, independent domain Noul questions allow multiple workflows, Score estimates risk, and Noul assesses ambiguity. Responses are validated and configured JEV failures never fall back to a heuristic.

The uncertainty threshold (`FLOWPILOT_UNCERTAINTY_THRESHOLD=0.35`) and domain Noul threshold (0.55) are provisional and uncalibrated. Business risk alone does not trigger complexity escalation. A confidence value is never treated as correctness evidence. Live JEV inference has now been verified with an authenticated request: the API reported `jev-1.14.0` and classified the supplier showcase correctly, with ambiguity triggering escalation. Payload/response contracts and HTTP failures are also covered by mocked tests. The local `.env` is loaded by the standard launcher; JEV credentials are removed from CLI child environments.

## Verification

`tests/test_models.py` covers policy snapshots, redaction, quota-only fallback, parser/schema failures, restricted fake CLI operation, five heuristic showcase classifications, unsupported input, official-shaped mocked JEV responses, configured-JEV failures, CLI classification, and risk/uncertainty separation. `tests/test_live.py` is opt-in and invokes an authenticated CLI to check evidence-dependent model action selection. See `docs/VALIDATION.md` for the final integrated results and known limitations.
