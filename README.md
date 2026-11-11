# FlowPilot

**Intelligent Enterprise Automation** · From incoming information to intelligent action.

A local enterprise operations console for investigating documents, emails and events with model-selected tools. Five workflows share one bounded asynchronous engine: supplier fraud, regulatory compliance, personal-data requests, IT assets and contract amendments.

FlowPilot uses the existing synthetic Harbourline Mutual Finance dataset: 250 cases across 44 interconnected enterprise tables. The dataset and original generator remain available; their full documentation is in [docs/DATASET.md](docs/DATASET.md).

## Start locally

Requires Python 3.11+, Node 20+, npm, and this source checkout. On the project owner's Mac, the existing `.venv` can be reused.

```sh
make setup
make build
make run
```

Open **http://127.0.0.1:8766**. To load the five bundled recordings as clearly labelled read-only replays, start with `.venv/bin/python -m flowpilot --import-recordings` instead. These files contain real recorded model/tool executions, not simulated AI responses. The Python server serves the built React application and API from one origin. Runtime SQLite data is stored in `.runtime/flowpilot.sqlite3` (ignored by Git). Override it with `FLOWPILOT_STATE_DIR`.

Equivalent commands:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix frontend install
npm --prefix frontend run build
.venv/bin/python -m flowpilot
```

For frontend development, leave the Python server running and run `make dev` in another terminal; Vite proxies `/api` to port 8766. An alternate backend port is supported with `python -m flowpilot --port 8767` (adjust the Vite proxy for development).

## Use the console

1. Select one of five curated examples, browse the generated inbox, or paste a new document.
2. Choose **Simulation** or **Live AI**, then start an investigation.
3. Read the business outcome and numbered recommendations first. Review any open questions or approval requests below them.
4. Expand **Supporting evidence**, **About this request** or **Investigation steps** when you want to see the records checked and how the result was reached. These sections start collapsed. Model/provider information, original findings and raw responses remain available in **Technical record** and each step’s technical details.
5. Approve or decline consequential simulated changes explicitly. Open prior runs from history or open a read-only recording from **Technical record**, where you can also download the complete JSON trace.
6. Run bounded evaluations against hidden ground truth from the Evaluation screen. Simulation scores and live model scores remain separate.

### Honest execution modes

| Mode | What runs | What it establishes |
|---|---|---|
| Simulation | Keyword routing and an observation-driven deterministic policy over the real mock APIs | Offline demonstration, UI/engine integration and governance. **No AI calls and no JEV response.** |
| Live AI | JEV or a real CLI classifier, followed by iterative structured decisions from authenticated local CLI models | Genuine model-selected tools and arguments, reconsidered after each returned batch. |
| Replay | Previously recorded events and results | No new classification, model or business-tool execution. Metrics belong to the original run. Approvals are read-only. |

Simulation is deliberately limited. Its outcome labels are heuristic, not ground truth; its measured evaluation accuracy may be poor. It is never a substitute for a live autonomous-tool demonstration.

## Models and configuration

Model roles, exact model identifiers, efforts, deadlines and ordered fallback routes live in [ai-models.toml](ai-models.toml). The routing design follows the owner's [JobGraph configuration](https://github.com/dav-rob/jobgraph/blob/main/ai-models.toml).

- `screening`: inexpensive classification when no JEV key is configured.
- `investigation`: inexpensive iterative tool selection.
- `escalated`: stronger reasoning for uncertainty, ambiguity or conflicting evidence.

Routes only fall back on an **explicit usage/rate limit**. Authentication errors, missing binaries, malformed output, tool activity and timeouts remain visible failures. Limited routes enter a process-local cooldown. Complexity escalation is recorded separately from provider fallback. Each run freezes its routing configuration. There are no paid model API integrations.

Live runs use the already authenticated local `claude`, `agy`, and `codex` subscriptions. Sign in through each CLI's normal interactive flow before running FlowPilot. Do not put subscription credentials in this repository. Provider restrictions and adapter verification are documented in [docs/MODELS.md](docs/MODELS.md).

### JEV

Set `TYPESAFE_API_KEY` (or `JEV_API_KEY`) in your local `.env`, or export it, to enable real JEV classification in live mode. `JEV_MODEL` defaults to `jev-latest`. Without a key, live classification uses a real local CLI; it is labelled accordingly. A failed configured JEV call is surfaced, never replaced with a synthetic response.

The adapter uses TypeSafe's official [System One API](https://docs.typesafe.ai/api/system-one): `POST https://api.typesafe.ai/v1/systemone`, bearer authentication, `state` and a map of typed questions. Choice selects the primary workflow; independent Noul questions allow multiple workflows and flag uncertainty; Score estimates business risk. Incoming documents remain untrusted data.

Confidence is not proof. Business risk and uncertainty are separate fields. The initial uncertainty threshold is provisional, **not calibrated**. The evaluator reports threshold sweeps when real confidence data is available; use labelled validation cases before tuning. No JEV credentials are needed for offline use.

Copy `.env.example` to `.env` and set the values you want. The standard launcher (`make run` or `python -m flowpilot`) loads this local file without executing shell code; exported environment variables take precedence. Restart the server after changing it. Keep `.env` private and out of Git. JEV credentials are excluded from investigation CLI child processes.

## Architecture

```text
React console → FastAPI → durable SQLite trace
                            ↓
                  JEV / CLI classification
                            ↓
                 bounded investigation loop
                   model structured action
                            ↓
             schema + workflow permission checks
                            ↓
                synthetic business tool registry
                  parallel independent reads
                            ↓
              observations → next model decision
                            ↓
                citation provenance validation
                            ↓
               outcome + human approval proposals
```

The owner explicitly allowed dropping Flow4AI. This implementation uses ordinary Python `asyncio` tasks, `gather` for independent read-only batches, serial simulated writes, and a single reusable engine. There is no unused workflow-framework dependency. The upstream [Flow4AI repository](https://github.com/dav-rob/Flow4AI) is unchanged.

| Module | Responsibility |
|---|---|
| `flowpilot/catalog.py` | Public inbox, attachments and showcase selection metadata |
| `flowpilot/classifier.py` | JEV, CLI and clearly labelled heuristic classification |
| `flowpilot/models.py` | Authenticated CLI adapters, model policy, cooldown/fallback |
| `flowpilot/engine.py` | Iterative investigation, limits, tracing, replay and approvals |
| `flowpilot/registry.py` | Callable tool discovery, argument schemas and workflow permissions |
| `flowpilot/simulation.py` | Explicit deterministic offline demonstration policy |
| `flowpilot/store.py` | SQLite durability and interrupted-run recovery |
| `flowpilot/evaluation.py` | Evaluator-only hidden-label access and measured metrics |
| `flowpilot/api.py` | Local HTTP API, concurrency limits and frontend serving |
| `flowpilot_data/` | Existing generator, partition-scoped tools and evaluator |
| `frontend/` | React/TypeScript console |

The model receives permitted tool descriptions and JSON schemas, document text and observed results. It returns validated structured actions; the runtime invokes ordinary Python functions. The CLI has no access to the project or ground truth during business inference. Observable operational rationales are recorded; private chain-of-thought is not requested or shown.

### Governance and durability

- Investigations are read-only by default; tool availability is enforced by workflow and permitted cross-domain categories.
- Arguments are schema validated before execution. Arbitrary code, SQL and unknown tool names are unavailable.
- Financial actions, permission changes, isolation, decommissioning, disclosure, correction and deletion require explicit human approval, even in simulation.
- Approval proposals are persisted with exact arguments; execution uses a fresh, single-use scoped HMAC token which is never persisted or returned. Runtime identity, retention and legal-hold guards are rechecked before execution; human approval cannot override those synthetic restrictions.
- Review cases and service tickets are harmless simulated records; they may be created during investigation and are included in the trace. No production integrations exist.
- High-risk live conclusions must leave a recorded review case, service ticket or approval proposal.
- Evidence citations and action references must have appeared in successful tool results and resolve to actual enterprise records or recorded simulated artifacts. Provenance validation does not establish that a model's interpretation is correct.
- Calls, iterations, model calls, context size, parallelism and wall-clock time are bounded and configurable. Provider errors and missing evidence remain visible.
- Complete meaningful events are committed to SQLite. A restart marks interrupted jobs failed; it does not quietly restart model calls. Completed traces, simulated state and pending approvals remain available.
- The server binds to loopback, rejects foreign hosts/cross-site mutations, and is intended for one local operator. It has no multiuser authentication or production deployment hardening.
- Stored inputs and evidence are synthetic. Prompts are not separately persisted; tool results are excerpted, and credentials/tokens are excluded. Public trace exports omit runtime session internals. Delete `.runtime/` while the server is stopped to reset local history.

## Tests and evaluation

```sh
make test
npm --prefix frontend test
make validate

# Requires authenticated local subscriptions and consumes subscription usage:
FLOWPILOT_LIVE_TESTS=1 .venv/bin/python -m pytest tests/test_live.py -v
```

The automated runtime suite covers the five offline showcases, observation-dependent arguments and branching, workflow permissions, schema errors, invented citations, durable human approvals, single-use execution, replay restrictions, cancellation and budgets, API validation, and evaluation integration. Adapter tests cover structured output, fallback rules and classifier behaviour. The opt-in live test changes a synthetic bank-account observation and checks that the real model concludes on matching records but selects further investigation for a discrepancy.

Bundled recorded live traces can be scored again without inference using `.venv/bin/python scripts/evaluate_recordings.py`.

The evaluation UI runs actual engine investigations before scoring them with the existing hidden-ground-truth evaluator. It reports routing accuracy, required tool coverage, relevant-call precision, redundant calls, outcome/evidence success, escalation, safety and recorded usage/latency. Missing costs or token counters remain unknown. Known IDs of newly created review/ticket artifacts are excluded from source-evidence benchmark citations; their creation remains visible in the run trace. It does not claim a paired first-pass-versus-escalated comparison without two measured systems; the existing offline evaluator supports such paired predictions.

Regenerate the existing dataset only when intended:

```sh
.venv/bin/python -m flowpilot_data generate --seed 42 --size 250 --out .
.venv/bin/python -m flowpilot_data validate --root .
```

`evaluation/` contains hidden labels and presenter fixtures. Investigation code never reads it. Showcase metadata contains only case IDs and workflow display labels; it is not supplied to the model. Training, validation and test partitions have separate records and scenario families. All legal and regulatory content is fictional test material.

## Development status

See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for scope and decisions, [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for the browser contract, and [docs/VALIDATION.md](docs/VALIDATION.md) for verified execution and remaining limitations.
