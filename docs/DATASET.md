# FlowPilot Synthetic Enterprise Dataset & Mock Tool Environment

This document describes the original dataset package. FlowPilot now includes a backend, live agent runtime and web console; see the root README for application setup. The scope below refers to the dataset package only.

A self-contained, deterministic synthetic enterprise dataset, mock tool library, and offline evaluation harness for demonstrating and evaluating **Flow4AI** business-process routing (**JEV**), multi-step LLM tool calling, and model escalation in a medium-sized UK financial-services organisation (*Harbourline Mutual Finance Ltd*).

> **Scope & Disclaimers**
> - **Data, mock tools, and offline evaluator only:** This dataset package provides the synthetic data generator, partition-scoped Python mock tools, and offline evaluation utilities. It does **not** include an AI agent implementation, model runner, or UI.
> - **No fabricated model scores:** Difficulty labels (`straightforward`, `moderate`, `difficult`) represent intended scenario complexity. No JEV confidence scores, model predictions, token counts, latencies, or costs are fabricated by the generator, and no real models have been evaluated yet.
> - **Synthetic policy fixtures (not legal advice):** All UK financial-services, GDPR/data-protection, regulatory compliance, procurement, and contract rules in this dataset are **synthetic test fixtures** created to test multi-step evidence gathering. Nothing in this repository constitutes legal, regulatory, or compliance advice or claims conformance with actual UK law.
> - **Fictional entities only:** All companies, people, sort codes, IBANs, VAT/company numbers, postcodes (`ZZ*`), domains (`*.example`), and emails are strictly synthetic.

---

## 1. Directory Structure & Public vs. Private Mount Boundary

When integrating with an agent or application runner, **mount only `data/` (or a single partition `data/partitions/<split>/`) into the agent environment**. Keep `evaluation/` strictly mounted only in the test/evaluation harness.

```text
.
├── flowpilot_data/                 # Python package (stdlib only, zero external runtime dependencies)
│   ├── __main__.py / cli.py        # CLI entry point (`python -m flowpilot_data ...`)
│   ├── generate.py                 # Deterministic builder & safe marker-checked installer
│   ├── planning.py                 # Quotas, 50/30/20 difficulty dealing & whole-family split holdout
│   ├── world.py / vocab.py         # Enterprise entity graph & synthetic UK financial-services vocabulary
│   ├── docs.py / noise.py          # Multi-format document renderer & controlled typo/OCR noise
│   ├── scenarios/                  # Coherent scenario families (5 domains + cross_domain + distractor)
│   ├── tools/                      # Partition-scoped mock tools & HMAC single-use ApprovalAuthority
│   ├── showcase.py                 # Showcase selector & presenter walkthrough runner
│   ├── validate.py                 # Schema, FK, path-replay, leakage & split-isolation validator
│   └── evaluate.py                 # Offline evaluator & paired system comparison (jev_only vs escalated)
├── data/                           # PUBLIC (AGENT-VISIBLE) MOUNT
│   └── partitions/
│       ├── train/                  # 150 cases (default size=250)
│       │   ├── cases.jsonl         # Opaque case_id, received_at, document & attachment file pointers
│       │   ├── inbox/              # Incoming documents (DOC-*.eml|.txt|.md|.event.json|.events.jsonl|.csv)
│       │   └── enterprise/*.jsonl  # 44 interconnected business tables queried by `flowpilot_data.tools`
│       ├── validation/             # 50 cases (disjoint scenario families & entity IDs)
│       └── test/                   # 50 cases (disjoint scenario families & entity IDs)
├── evaluation/                     # PRIVATE (EVALUATOR-ONLY) MOUNT — NEVER EXPOSE TO AGENT
│   ├── ground_truth/               # train.jsonl, validation.jsonl, test.jsonl (labels, facts, paths, outcomes)
│   ├── manifests/                  # dataset_manifest.json, splits.json
│   ├── showcase/                   # showcase_cases.json, SHOWCASE_GUIDE.md (presenter fixtures)
│   └── schema/prediction_schema.md # Specification for caller-provided prediction JSONL files
└── tests/                          # Stdlib unittest suite (generator, tools, approvals, evaluator, regressions)
```

---

## 2. Data Model & Default Dataset Quotas (`seed=42`, `size=250`)

### Workflow Groups & Quotas
| Group | Primary Category | Cases (`size=250`) | Train / Val / Test | Typical Triggers & Enterprise Tables |
|---|---|---:|---:|---|
| `supplier_fraud` | `supplier_fraud` | 40 | 24 / 8 / 8 | Invoices, bank-detail changes, urgent payment instructions (`suppliers`, `supplier_bank_accounts`, `invoices`, `purchase_orders`, `goods_receipts`, `supplier_changes`, `callback_log`, `email_messages`, `fraud_cases`) |
| `regulatory_compliance` | `regulatory_compliance` | 40 | 24 / 8 / 8 | Supervisory notices & policy updates (`policies`, `systems`, `controls`, `control_catalogue`, `databases`, `access_grants`, `audit_findings`, `control_exceptions`) |
| `gdpr_data` | `gdpr_data` | 40 | 24 / 8 / 8 | Erasure, SAR/access, correction & third-party requests (`customers`, `customer_products`, `identity_verifications`, `datasets`, `data_locations`, `retention_rules`, `legal_holds`, `data_requests`, `authority_letters`) |
| `it_asset` | `it_asset` | 40 | 24 / 8 / 8 | Unrecognised cloud assets, CMDB discrepancies & alerts (`cmdb_items`, `cloud_resources`, `deployments`, `changes`, `security_alerts`, `employees`, `tickets`) |
| `contract_risk` | `contract_risk` | 40 | 24 / 8 / 8 | Contract renewals, amendments & retrospective approvals (`contracts`, `contract_versions`, `supplier_risk`, `delegated_authority`, `privacy_assessments`, `approval_workflows`) |
| `cross_domain` | Primary + Secondary | 25 | 15 / 5 / 5 | Multi-workflow incidents legitimately requiring tools and outcomes from two domains |
| `distractor` | `out_of_scope` | 25 | 15 / 5 / 5 | Irrelevant vendor pitches, misrouted messages, or insufficiently specified requests where abstention/clarification is appropriate |
| **Total** | | **250** | **150 / 50 / 50** | **Intended difficulty:** `125` straightforward (50%), `75` moderate (30%), `50` difficult (20%) |

### Document & Record Formats
- **Public Case Index (`data/partitions/<split>/cases.jsonl`):** Contains only `case_id` (`IN-*`), `partition`, `received_at`, `document` (`document_id`, `path`, `media_type`, `bytes`, `sha256`), and `attachments`.
- **Incoming Documents (`inbox/DOC-*`):** Rendered across `.eml` (`message/rfc822`), `.txt` (`text/plain`), `.md` (`text/markdown`), `.event.json` (`application/json`), `.events.jsonl` (`application/x-ndjson`), and `.csv` (`text/csv`) attachments, with controlled typo/OCR noise (`clean`, `minor_noise`, `heavy_ocr`) that preserves entity identifiers needed for tool lookup.
- **Enterprise Records (`enterprise/*.jsonl`):** 44 JSONL tables with stable cross-referenced IDs (`SUP-*`, `INV-*`, `PO-*`, `POL-*`, `SYS-*`, `CUS-*`, `CI-*`, `CLD-*`, `CTR-*`, etc.). A hidden table (`service_status.jsonl`) configures deterministic per-case tool outages (`down_for_first_n_calls` or `down_with_alternate`) and is never disclosed as a searchable record by any public tool.

---

## 3. CLI Commands

All commands run with the standard library using `.venv/bin/python` or `python3`:

```bash
# 1. Deterministically generate the default 250-case dataset (seed=42)
.venv/bin/python -m flowpilot_data generate --seed 42 --size 250 --out .

# 2. Validate quotas, foreign-key references, live tool-path replay, split isolation & zero label leakage
.venv/bin/python -m flowpilot_data validate --root .

# 3. List or run the live-demo presenter walkthrough for the 5 curated showcase cases
.venv/bin/python -m flowpilot_data showcase --list
.venv/bin/python -m flowpilot_data showcase
.venv/bin/python -m flowpilot_data showcase --case IN-B148DF6144
.venv/bin/python -m flowpilot_data showcase --workflow it_asset

# 4. Run the offline evaluator on caller-provided predictions (single system or paired comparison)
.venv/bin/python -m flowpilot_data evaluate --predictions path/to/predictions.jsonl --partition test
.venv/bin/python -m flowpilot_data evaluate --predictions path/to/paired_predictions.jsonl --compare jev_only jev_plus_escalation

# 5. Run the full stdlib unittest suite
.venv/bin/python -m unittest discover -s tests -v
```

---

## 4. Inspecting Inputs, Calling Mock Tools & Async / Approval Usage

### Inspecting a Public Case & Calling Tools (`sync` and `async`)
`flowpilot_data.tools` opens a single partition directory (`data/partitions/<split>`) and scopes a session to one `case_id`. It never loads `evaluation/`. Both synchronous `session.call(...)` and async-compatible `await session.acall(...)` (for Flow4AI asynchronous jobs) return structured `{ok, tool, data | error}` envelopes:

```python
import asyncio
from pathlib import Path
from flowpilot_data.tools import open_session
from flowpilot_data.util import read_jsonl

# 1. Read agent-visible case metadata and incoming document text
cases = {c["case_id"]: c for c in read_jsonl(Path("data/partitions/train/cases.jsonl"))}
case = cases["IN-B148DF6144"]
doc_text = Path("data/partitions/train", case["document"]["path"]).read_text(encoding="utf-8")

# 2. Open a case-scoped tool session over the train partition
session = open_session("data", partition="train", case_id="IN-B148DF6144")

# 3. Call tools synchronously or via async `acall`
inv_res = session.call("search_invoices", invoice_number="SI-79253")
sup_id = inv_res["data"]["matches"][0]["supplier_id"]

sup_res = asyncio.run(session.acall("get_supplier_record", supplier_id=sup_id))
print(sup_res["data"]["supplier"]["onboarding_checks"])  # -> "incomplete"
```

### Sensitive Actions & Explicit Mock Approval (`ApprovalAuthority`)
All mutations (`create_review_case`, `create_ticket`, and the 10 sensitive financial/security/data tools in `SENSITIVE_TOOLS`) operate strictly on in-memory session state (`session.state`) and never modify disk files. Any sensitive action called without a valid token fails with `APPROVAL_REQUIRED`.

Tokens are issued by `ApprovalAuthority` (owned by the harness/human approver, never exposed as an agent tool), signed with a runtime HMAC secret, bound to `(case_id, tool_name, canonical_args_hash)`, and consumed on first use (`APPROVAL_INVALID`, `APPROVAL_WRONG_SCOPE`, `APPROVAL_REUSED`):

```python
from flowpilot_data.tools import ApprovalAuthority, open_session

authority = ApprovalAuthority()  # or ApprovalAuthority(auto_policy=lambda req: True) for automated tests
session = open_session("data", partition="train", case_id="IN-B148DF6144", authority=authority)

# Unapproved sensitive call is rejected
unapproved = session.call("place_payment_hold", invoice_id="INV-E551FF7F", reason="Suspected executive impersonation")
assert unapproved["error"]["code"] == "APPROVAL_REQUIRED"

# Agent submits an approval request
req = session.call(
    "request_approval",
    action="place_payment_hold",
    arguments={"invoice_id": "INV-E551FF7F", "reason": "Suspected executive impersonation"},
    justification="Invoice SI-79253 came from lookalike domain harbouriine.example; supplier onboarding incomplete.",
)
request_id = req["data"]["request_id"]

# Human / harness inspects pending requests and approves, issuing a single-use scoped token
token = authority.decide(request_id, approve=True, approver="fraud-ops-lead")

# Agent executes the approved action once
held = session.call(
    "place_payment_hold",
    invoice_id="INV-E551FF7F",
    reason="Suspected executive impersonation",
    approval_token=token,
)
assert held["ok"] and held["data"]["simulated"] is True
```

---

## 5. Five Curated Showcase Cases (`seed=42`, `train` Partition)

Five cases—one per workflow domain—are deterministically selected from `train` (preserving `validation` and `test` for evaluation) and documented in [`evaluation/showcase/SHOWCASE_GUIDE.md`](evaluation/showcase/SHOWCASE_GUIDE.md) and [`evaluation/showcase/showcase_cases.json`](evaluation/showcase/showcase_cases.json).

> **Important:** The `example_path` recorded in `evaluation/showcase/showcase_cases.json` and replayed by `python -m flowpilot_data showcase` is a **presenter/evaluator fixture** illustrating one valid investigation path. It is never visible to the agent; each case supports multiple valid investigation paths, and an agent selects tools dynamically.

| Workflow | Case ID | Input Format | Presenter Example Path (Fixture) | Key Evidence Discovered | Expected Outcome |
|---|---|---|---|---|---|
| `supplier_fraud` | `IN-B148DF6144` | `.event.json` | `search_invoices` $\rightarrow$ `get_supplier_record` $\rightarrow$ `verify_email_origin` *(recovers from transient `SERVICE_UNAVAILABLE`)* | `SUP-47D4A998` (incomplete urgent onboarding), `MSG-0C0E250E` (`harbouriine.example` spoofing) | `hold_payment_and_open_fraud_case` (`critical` risk) |
| `regulatory_compliance` | `IN-4988DE6162` | `.md` | `search_records` $\rightarrow$ `discover_affected_systems` $\rightarrow$ `get_access_grants` | `POL-EACCD525`, `SYS-B443E6D3` (in-scope), `ACG-5257D030` (human privileged grant without MFA) | `open_audit_item_gap_found` (`high` risk) |
| `gdpr_data` | `IN-D687B92A2F` | `.events.jsonl` | `find_customer` $\rightarrow$ `get_audit_trail` $\rightarrow$ `verify_identity_status` | `CUS-B9609E8D`, `LOG-4A0469CE` & `LOG-BB08C7BC` (suspicious device changes), `IDV-F54272E7` (failed IDV) | `refer_to_security_review` (`high` risk) |
| `it_asset` | `IN-F8352D982B` | `.txt` | `search_assets` $\rightarrow$ `get_security_alerts` $\rightarrow$ `get_cmdb_item` | `CI-B33F4001` (registered MAC differs), `ALT-3733ABEF` (rogue host masquerade), `TKT-1B2F7E43` | `isolate_and_open_incident` (`critical` risk) |
| `contract_risk` | `IN-8649D7CEB6` | `.eml` | `find_contracts` $\rightarrow$ `get_approval_workflow` $\rightarrow$ `get_contract` | `CTR-8649A3D3` (already executed), `WFL-DE949059` (approvals incomplete prior to signature) | `escalate_to_senior_approval` (`high` risk) |

---

## 6. Split Isolation & Realistic Limitations

- **Whole-family holdout:** Each workflow has multiple distinct scenario families (`family_id`). During generation, `planning.assign_families` assigns entire scenario families exclusively to `train`, `validation`, or `test`. No `family_id` appears in more than one partition (`evaluation/manifests/splits.json`).
- **Entity & text isolation:** Each partition is built in an independent `World(seed, partition)` with disjoint entity IDs (`SUP-*`, `CUS-*`, `CI-*`, `CTR-*`, etc.). `validate.py` verifies zero shared entity IDs, zero shared `family_id`s, zero leaked ground-truth tokens, and bounds cross-partition masked 4-gram Jaccard similarity ($\le 0.41$ on default `seed=42`).
- **Limitations of synthetic splits:** Although scenario families and entity graphs are disjoint across `train`, `validation`, and `test`, all partitions are generated by the same codebase, document templates, noise rules, and synthetic enterprise schema. Held-out test metrics therefore measure generalisation to unseen scenario families and evidence chains within this synthetic domain, not real-world production distribution shift.
- **Evaluation schema:** See [`evaluation/schema/prediction_schema.md`](evaluation/schema/prediction_schema.md) for the exact JSONL format accepted by `python -m flowpilot_data evaluate`, including optional runtime `confidence` for escalation-threshold calibration and paired `jev_only` vs. `jev_plus_escalation` comparison.

End-to-end latency is scored only from caller-provided `usage.latency_ms`. The sum of tool-call durations is reported separately because it excludes model reasoning and can overlap during parallel calls. For prediction files containing multiple systems, choose `--system <name>` or `--compare <a> <b>`.

The default validator reports three repeated masked evidence shapes (standard passed identity checks, erasure-location records and active legal holds). Their entity IDs and scenario families are separate; these generic business states are shared vocabulary, not reused case records.
