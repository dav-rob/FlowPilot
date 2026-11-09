# FlowPilot console

React, TypeScript, and Vite. All application data comes from same-origin `/api` endpoints described in `../docs/API_CONTRACT.md`; there are no frontend fixtures or fabricated traces.

```sh
cd frontend
npm install
npm run dev
```

The development server proxies `/api` to `http://127.0.0.1:8766`. The backend must be running separately.

```sh
npm run build
```

The production build is written to `frontend/dist`, which the backend serves directly. No external fonts, images, analytics, or services are loaded by the interface.

- **Investigations:** real showcase cases, all dataset partitions, custom input, explicit Live AI or deterministic Simulation mode.
- **Execution:** one-second polling while active or awaiting approval; classification, escalation, collapsible batches, recorded arguments/results, outcomes, evidence, simulated approvals, cancellation, and JSON downloads.
- **History:** stored investigations and explicitly labelled read-only trace replay; pending approvals cannot execute from recordings.
- **Evaluation:** bounded runs of 1–25 cases, progress, original nested metrics, per-case results, and trace drill-down. Simulation metrics are explicitly distinguished from live model performance.
- **Registry:** backend tool metadata, domain and permission filters, and argument schemas.

Navigation uses URL hashes, so stored run details can be bookmarked. Documents and tool results are always rendered as text. API and polling failures are surfaced without inventing replacement data.
