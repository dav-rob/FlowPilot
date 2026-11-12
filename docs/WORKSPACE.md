# Finance workspace

The landing page is a business dashboard built from recorded investigations.
It shows pending decisions, cases requiring follow-up, documents being checked,
and documents available in the example inbox. Business-area cards filter cases;
they never choose the agent's tools or determine how JSON is parsed.

## Normal document flow

1. Open **Documents** to read an example email or event and its attachments.
2. Select **Process document**. The original input is sent unchanged to the shared
   live investigation engine, which classifies the request and selects its checks.
3. Read the findings and recommendations in **Cases & findings**.
4. Open a pending decision to review its evidence and approve or decline a
   simulated change.

The inbox uses the supplied 250 example documents. No mailbox, watched folder or
webhook feed is connected. Processing is explicitly initiated from a document;
opening the dashboard or inbox never starts model calls.

JSON, line-delimited JSON, email, Markdown and text inputs are presented as readable
correspondence. This presentation parser has no role in classification or routing.
Original inputs remain available in each investigation's document and technical record.

## Case counts

Repeated checks of the same document are grouped into one case. Known documents
use their partition and case ID; identical custom inputs use a content fingerprint.
The most recent investigation supplies the headline finding. Pending approvals
from earlier investigations remain visible and link to their exact requests.

Developer tests, evaluations and deterministic simulations are excluded from
business totals. Saved live examples are displayed only when the original
investigation is unavailable, labelled read-only, and never counted as actionable
approvals. Findings with unresolved questions or recommended follow-up remain
visible; completing an AI investigation does not establish that its business
issues have been resolved.

## Developer view

Append `?developer=true` before the hash to reveal the test workbench, complete
execution history, evaluation and tool registry:

- Local: `http://127.0.0.1:8766/?developer=true#workbench`
- Shared: append `?developer=true#workbench` to the existing `/flowpilot/` URL.

The workbench retains the sample selector, original JSON/input inspector and
Live AI/Simulation settings. It creates runs with `purpose: "test"`; evaluations
create `purpose: "evaluation"`. Normal document processing uses `"business"`.
Historical unlabelled live runs retain their business classification.

This query parameter controls navigation visibility, not authentication or API
permissions. Choose **Developer view · Exit** to return to the normal workspace.
Old `#investigations` links open Overview; normal `#history` links open Cases & findings.
