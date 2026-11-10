# FlowPilot implementation status

## Delivered

All five workflows run through the shared Python investigation engine and 63 ordinary callable enterprise tools. The React operations console provides the case gallery, custom input, live execution timeline, results, approvals, history/replay, registry, and evaluation. SQLite persists meaningful events, simulated state and approval proposals. Five successful live recordings are included for credential-free replay.

The supplied 250-case dataset, generator and mock enterprise APIs were retained. Ground truth is loaded only by the evaluator, never the investigation runtime or model adapters. The upstream Flow4AI repository was not modified.

## Decisions

- Use FastAPI, React/TypeScript/Vite, SQLite and `asyncio`; the owner explicitly permitted omitting Flow4AI. Independent read-only calls run in parallel; simulated writes are serialised.
- Models return structured action proposals. The runtime validates schemas, tool/workflow permissions, references and action constraints. No arbitrary shell, SQL, production integration or tool implementation lives in a business prompt.
- Live, deterministic simulation and recorded replay are distinct. Replays preserve source status/mode and cannot execute approvals.
- JobGraph-style TOML policies separate complexity escalation from quota-only fallback. A run freezes its policy; errors remain observable.
- Keep screening at Flash low; use Flash medium for investigation after observed low-effort protocol failures. Start stronger reasoning at Argon high after a Claude structured-action failure. All routes remain configurable.
- High-risk live outcomes require a recorded handoff. Consequential changes require human approval and synthetic identity/retention/legal-hold guards. A failed investigation cannot approve pending changes.
- Validate citation provenance without claiming model interpretations are proven correct. Preserve failures and honest evaluation metrics.
- Serve on loopback port 8766 because the owner's existing service occupies 8765.

## Work completed

1. Inspected the supplied data/tools, Flow4AI reference, JobGraph routing and installed CLI capabilities.
2. Established module/API boundaries and delegated independent provider/frontend tasks.
3. Built supplier fraud vertically, then generalised one engine across all five domains.
4. Integrated the classifier, model routes, governed tool execution, persistence and web console.
5. Tested evidence-dependent branching with real CLI inference; recorded five successful live showcases.
6. Reviewed runtime edge cases and corrected cancellation, empty evidence, approval constraints, replay, and outcome-scope issues.
7. Verified API/browser behaviour, responsive/accessibility checks, reproducible recorded evaluation, build and automated tests.
8. Documented limitations, verified live JEV, and published the reviewed source to https://github.com/dav-rob/FlowPilot.

## Delegation and integration

- Lead: architecture, engine, registry, governance, persistence, API, simulation integration, evaluation, recording/replay, regression tests and final verification.
- Antigravity CLI / Gemini 4 Argon high: model adapters, classifier, TOML policy, adapter tests and initial model documentation. Its first bounded task timed out; an exact-session follow-up completed the remaining tests/docs. The lead reviewed and corrected documentation against the actual implementation.
- Claude CLI / Sonnet 5.5 high: initial frontend delegation was rejected by an explicit subscription usage limit before editing.
- Codex CLI / GPT-6.1 Sol high: frontend implementation, build and browser/accessibility checks. The bounded task reached its deadline during final narrow-layout polish; the lead reviewed the delivered code, completed remaining integration fixes and reran the build.
- Independent runtime review: identified concrete cancellation, approval, citation, cross-domain scoring and malformed-argument issues; corrections are covered by regressions.

## Remaining work

No required implementation work remains for the local demonstration. Verified limits and further evaluation work are documented in `docs/VALIDATION.md`: live JEV authentication and classification are verified; confidence thresholds need broader calibration, and stronger cross-domain conclusions can still fail evidence validation. Production integrations, deployment and multiuser operation are outside scope.
