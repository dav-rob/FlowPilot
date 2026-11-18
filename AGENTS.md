# FlowPilot Presentation & Domain Rules

## Ordinary UI Presentation
- Ordinary user-facing surfaces—including the user profile menu and dialogs, header, footer, overview, inbox, processed cases, approvals, case results, execution traces, and evals—must **not** carry `demo`, `sample`, `fictional`, or `synthetic` provenance labels, badges, or repetitive disclaimers (for example: `Demo profile`, `Sample workspace profile`, `Sample / demo user`, `This demo profile is for display`).
- Do **not** add repetitive origin lectures or environment disclaimers to ordinary workflows, cards, or dialogs.
- General origin and environment explanation belongs **only** on the About page (`AboutPage` in `frontend/src/Workspace.tsx`).

## Preserved Operational Distinctions
- **Execution modes**: Preserve clear, accurate distinctions between `Live API` (actual AI model calls), `Simulation` (deterministic rules, no AI model calls), and `Recorded replay` (read-only view of an earlier saved run with no new AI calls or record changes).
- **Simulated consequential actions**: Keep honest labels where consequential business actions are simulated (e.g., simulated changes/actions within the simulation).
- **Evaluation vs. business purposes**: Preserve distinctions between test workbench / evaluation runs and operational business cases, as well as useful evaluation and benchmark terminology (e.g., distinguishing a development sample from a held-out benchmark).

## Data, Domain & Identity Integrity
- Never alter original source documents, supporting evidence, raw traces, underlying records, or evaluation ground truth.
- Preserve legitimate domain terminology such as `synthetic identity fraud` or `synthetic-identity fraud`.
- Do not invent identity-based permissions enforcement or fabricated multiuser approval authority; approval rules apply to every request.
- Prefer handling legacy backend provenance phrasing in presentation helpers (such as `suppressProvenanceProse` in `frontend/src/presentation.ts`) or direct UI copy rather than mutating raw records or traces.

## Verification
- Future UI and copy changes must follow these rules and pass the frontend regression checks (`cd frontend && npm test` and `cd frontend && npm run build`).
