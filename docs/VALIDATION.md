# Validation — 9 November 2026

## Automated checks

- `.venv/bin/python -m pytest -q`: **52 passed, 1 skipped**. The skipped test requires live subscription inference and was run separately below. One upstream Starlette/httpx deprecation warning remains; it does not affect execution.
- `FLOWPILOT_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live.py -q`: **1 passed**, using the final Flash medium investigation route. The same input and instructions receive matching versus conflicting synthetic bank observations; the model concludes on matching records and selects follow-up actions for the discrepancy. This is real CLI inference, not a scripted responder.
- `npm --prefix frontend run build`: TypeScript and Vite production build passed.
- `.venv/bin/python -m flowpilot_data validate --root .`: **250 cases, 1,356 replayed evidence paths, zero errors**. The existing validator reports one warning: three masked decisive-evidence shapes recur across partitions as boilerplate. Dataset generation and enterprise records were preserved.

Runtime tests cover dependent arguments, evidence-dependent branching, workflow/schema rejection, outcome-scope rejection, citation validation (including injected tool text with nonexistent IDs), protocol correction, stronger-role selection, high-risk review handoffs, budgets, cancellation (including evaluation and CLI-preflight races), durable single-use approval, legal-hold/retention/identity restrictions, failed-run approval rejection, and read-only replay/import. API and evaluator integration are included.

## Five real live showcases

The following runs used Flash low for CLI classification and Flash medium for investigation. Public JSON recordings are checked into `examples/traces/`; no ground truth, approval tokens or raw provider transcripts are included. These are curated successful executions after integration fixes, not a measure of success across every development attempt.

| Workflow | Tool calls | Model requests | Recorded business outcome | Final status |
|---|---:|---:|---|---|
| Supplier fraud | 12 | 5 | Hold payment and open fraud case | Awaiting human approval |
| Policy/compliance | 12 | 7 | Open audit item for control gap | Completed |
| Personal-data request | 7 | 6 | Refer to security review | Completed |
| IT asset | 11 | 6 | Isolate and open incident | Awaiting human approval |
| Contract risk | 7 | 5 | Escalate to senior approval | Completed |

The investigations created actual simulated review cases, tickets or approval proposals through model-selected tools. Consequential payment/security changes remain pending; no production system exists. Each run took approximately 107–206 seconds, dominated by CLI inference. Model usage is recorded; absent monetary costs remain unknown.

To import the recordings as **read-only replay** without new inference:

```sh
.venv/bin/python -m flowpilot --import-recordings
```

To reproduce their scores without making model or tool calls:

```sh
.venv/bin/python scripts/evaluate_recordings.py --out .runtime/recorded-evaluation.json
```

Measured on these five curated training cases: exact multilabel match **100%**, outcome accuracy **100%**, evidence-grounded outcome accuracy **100%**, required-evidence group coverage **80%**, relevant-call precision **81.63%**, unknown source citations **0**, and unsafe cases **0**.

**Primary routing accuracy is only 20%**, because the existing evaluator expects initial abstention for four of these ambiguous inputs. Expected stronger-model escalation was also missed on all five. The classifier selected the right workflow labels but was overconfident about initial routing. These results are intentionally preserved, not relabelled as perfect classification. They do not calibrate either CLI or JEV thresholds and do not establish held-out performance.

## Complexity escalation and failure handling

A live custom two-domain procurement input produced both `supplier_fraud` and `contract_risk`, uncertainty 0.40, and explicit complexity escalation. The stronger Argon high route performed 24 tool calls across both processes. Its final response cited an unobserved supplier ID; provenance validation rejected the conclusion. The failed run remains in local history, and its pending actions cannot be approved. It is not included among the successful showcase recordings.

An earlier Claude escalation probe emitted native enterprise tool-use blocks instead of the structured JSON protocol and was rejected by the adapter. The default escalated route now explicitly starts with Antigravity Argon. This configuration decision is separate from automatic quota-only fallback. Low-effort Flash also produced malformed action envelopes in early investigations; standard investigation now uses medium effort, with at most two visible same-model protocol corrections.

## Browser checks

Verified against the actual API: showcase/gallery selection, all 250 cases and search, pasted input, simulation launch and all five workflows, trace filters and expandable arguments/results, outcome/evidence rendering, approval execution, run history, replay, registry filtering, evaluation and trace downloads. No browser JavaScript errors were observed. Accessibility checks found no reported violations on the four main screens and execution view. Common 390/768/1024/1440 layouts were checked; a final native-browser check at 320px confirmed no horizontal overflow. On narrow screens completed outcomes appear before the long execution trace.

The native browser confirmed a simulated approval recorded an executed result. It then confirmed an imported live recording displays **Recorded replay**, preserves **source: Awaiting approval / Live**, and offers no approval buttons. The console is left open on the workflow gallery.

## Remaining limits

- No JEV key was configured, so the live TypeSafe endpoint has not been exercised. Official-shaped requests, responses and failures are covered by mocked contract tests; live CLI classification is verified and clearly labelled as not JEV.
- Codex catalog discovery and parser checks are covered; its application tool-registry preflight and a complete live business investigation remain unverified. Claude's structured-action limitation is recorded above.
- Routing thresholds remain provisional. Run broader labelled validation before tuning; the existing evaluator supports confidence sweeps and paired-system comparisons, but the UI does not claim a measured paired comparison without two systems.
- Cross-domain model reliability needs further evaluation. The runtime supports multiple permitted workflows and per-workflow outcomes, and rejects unsupported citations rather than manufacturing success.
- This is a single-operator loopback application over synthetic records, without production integrations, multiuser authentication or distributed execution. Restarted active jobs are marked failed rather than automatically resumed.
- No Git remote was configured. Delivery commits are local.
